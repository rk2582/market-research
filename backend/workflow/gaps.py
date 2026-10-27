"""M14 research-more loop: find the gaps in the checked evidence (in code, fixed rules), brief the Researcher
for ONE targeted round, and merge what it finds.

Gap rules (plan D27 — code decides, the model only fills):
- both: a competitor/player with fewer than 2 confirmed claims, or none from its own website;
- both: a trend, price or recent-news claim whose only dated source is older than 3 years;
- company: no confirmed pricing or funding claim for the company;
- market: a missing snapshot topic; market size or growth backed only by research-firm estimates;
  fewer than 3 players with a confirmed price.
At most MAX_GAPS go into one round, most important first.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from schemas.findings import Competitor, GapFindings, MarketFindings, ResearchFindings, SourcedText
from schemas.report import CheckedClaim, Claim
from schemas.research import SourceCreate
from workflow.claims import (
    COMPANY_FIELDS,
    COMPETITOR_FIELDS,
    INDUSTRY_SUBJECT,
    MARKET_FIELDS,
    NOT_PUBLIC,
    Findings,
    _host,
    build_claim,
    competitors_of,
    is_estimate,
    is_primary_source,
    is_research_firm,
    old_source_year,
    primary_hosts,
    site_root,
    with_competitors,
)
from workflow.report_assembler import numbers_in
from workflow.source_harvest import url_key

MAX_GAPS = 8
CONFIRMED = ("supported", "partially_supported")
MIN_CONFIRMED_FACTS = 2
MIN_PLAYERS_WITH_PRICE = 3
PLAYER_FIELDS = tuple(name for name, _ in COMPETITOR_FIELDS)

# What to look for when a market-snapshot topic is missing ("{region}" is filled in).
TOPIC_ASK = {
    "market_size": "the size of the market in {region} (value or volume, with year), ideally from an official source",
    "growth": "growth of the market in {region} (rates, trends over years, forecasts with who makes them)",
    "customers_demand": "who buys in {region}, how much and how often, and what drives demand",
    "prices": "typical retail prices per unit in {region}, with dates",
    "supply_chain": "how the product is sourced, made and distributed in {region}",
    "regulation": "licences, standards and rules for this business in {region}",
    "costs_margins": "start-up costs and typical margins (only if public)",
    "barriers": "what makes entry hard in {region} (capital, brands, distribution, rules)",
}
# Most important first: a newcomer needs size and prices before supply-chain detail.
MARKET_TOPIC_ORDER = (
    "market_size",
    "prices",
    "growth",
    "customers_demand",
    "regulation",
    "barriers",
    "supply_chain",
    "costs_margins",
)


@dataclass(frozen=True)
class Gap:
    key: str  # stable id, used to tell whether the gap was filled
    about: str  # the company, player or market the statements are about (exact name)
    fields: tuple[str, ...]  # where the statements may go (GapField values)
    ask: str  # what to find, in plain words


@dataclass
class GapMerge:
    findings: Findings
    claims: list[Claim]  # new claims, numbered after the existing ones (not yet fact-checked)
    notes: list[str] = field(default_factory=list)


def _confirmed(claims: Iterable[CheckedClaim]) -> list[CheckedClaim]:
    return [c for c in claims if c.verdict in CONFIRMED]


def _from_own_site(claim: Claim, website: str | None) -> bool:
    return bool(website) and any(_host(u) == _host(website) for u in claim.source_urls)  # type: ignore[arg-type]


def _player_gap(player: Competitor, claims: list[CheckedClaim], *, want_price: bool, market: bool) -> Gap | None:
    mine = [c for c in claims if c.section.startswith("competitor.") and c.subject == player.name]
    asks: list[str] = []
    if not player.website:
        asks.append("find its own website and read it")
    elif not any(_from_own_site(c, player.website) for c in mine):
        asks.append(f"read its own website ({player.website})")
    if len(mine) < MIN_CONFIRMED_FACTS:
        asks.append("what it sells and to whom")
    if want_price and not any(c.label == "Pricing" for c in mine):
        asks.append("its prices per unit" if market else "its pricing")
    if not asks:
        return None
    ask = f"{player.name}: {'; '.join(asks)}"
    return Gap(key=f"player:{player.name}", about=player.name, fields=PLAYER_FIELDS, ask=ask)


def _section_field(claim: CheckedClaim, market: bool) -> str:
    if claim.section == "industry":
        return "trends" if market else "industry_context"
    return claim.section.split(".", 1)[1]


def _old_source_gaps(claims: list[CheckedClaim], now_year: int, market: bool) -> list[Gap]:
    """One gap per subject + section whose stale-prone claims rest only on old pages."""
    gaps: dict[str, Gap] = {}
    for claim in claims:
        year = old_source_year(claim, now_year)
        if year is None:
            continue
        same_place = [c for c in claims if c.subject == claim.subject and c.section == claim.section]
        if any(c.source_year is not None and old_source_year(c, now_year) is None for c in same_place):
            continue  # a current source already covers this
        key = f"old:{claim.subject}:{claim.section}"
        about = claim.subject
        gaps.setdefault(
            key,
            Gap(
                key=key,
                about=about,
                fields=(_section_field(claim, market),),
                ask=f'A current source (last 2 years) for: "{claim.text}" — the only source is from {year}.',
            ),
        )
    return list(gaps.values())


def find_gaps(findings: Findings, claims: list[CheckedClaim], now_year: int, profiled: Iterable[str] = ()) -> list[Gap]:
    """The gaps in the checked evidence, most important first, at most MAX_GAPS. `profiled`: competitors /
    players that already had their own researcher (M15) — a second round would only repeat that work."""
    skip = set(profiled)
    confirmed = _confirmed(claims)
    market = isinstance(findings, MarketFindings)
    players = competitors_of(findings)
    gaps: list[Gap] = []
    if isinstance(findings, MarketFindings):
        region = findings.market_name
        primary = primary_hosts(findings)
        present = {c.section.removeprefix("market.") for c in confirmed if c.section.startswith("market.")}
        with_price = sum(1 for p in players if any(c.subject == p.name and c.label == "Pricing" for c in confirmed))
        topic_gaps: list[Gap] = []
        for name in MARKET_TOPIC_ORDER:
            label = dict(MARKET_FIELDS)[name]
            if name not in present:
                ask = TOPIC_ASK[name].format(region=region)
                topic_gaps.append(Gap(key=f"topic:{name}", about=region, fields=(name,), ask=f"{label}: {ask}"))
            elif name in ("market_size", "growth") and all(
                is_estimate(c, primary) for c in confirmed if c.section == f"market.{name}"
            ):
                topic_gaps.append(
                    Gap(
                        key=f"official:{name}",
                        about=region,
                        fields=(name,),
                        ask=f"{label}: an official figure (government statistics, regulator, industry body or"
                        " co-operative) — so far only research-firm estimates",
                    )
                )
        player_gaps = [
            g
            for p in players
            if p.name not in skip
            and (g := _player_gap(p, confirmed, want_price=with_price < MIN_PLAYERS_WITH_PRICE, market=True))
        ]
        # size and prices first, then the players, then the other topics
        first = [g for g in topic_gaps if g.fields[0] in ("market_size", "prices")]
        rest = [g for g in topic_gaps if g not in first]
        gaps = [*first, *player_gaps, *rest]
    else:
        company = findings.company.name
        mine = {c.label for c in confirmed if c.section.startswith("company.")}
        if "Pricing" not in mine:
            gaps.append(Gap(key="company:pricing", about=company, fields=("pricing",), ask=f"{company}: its pricing"))
        if "Funding" not in mine:
            gaps.append(
                Gap(key="company:funding", about=company, fields=("funding",), ask=f"{company}: funding or ownership")
            )
        gaps += [
            g
            for p in players
            if p.name not in skip and (g := _player_gap(p, confirmed, want_price=False, market=False))
        ]
    gaps += _old_source_gaps(confirmed, now_year, market)
    return gaps[:MAX_GAPS]


def gap_brief(gaps: list[Gap], findings: Findings, scope: dict | None) -> str:
    """The round-2 prompt: exactly what to find, numbered."""
    if isinstance(findings, MarketFindings):
        subject = findings.market_name
        if scope:
            subject += f" (product: {scope.get('product')}; region: {scope.get('region')})"
    else:
        subject = findings.company.name
        if findings.company.website:
            subject += f" ({findings.company.website})"
    lines = [f"Second research round for: {subject}.", "Find ONLY these gaps:"]
    for number, gap in enumerate(gaps, start=1):
        lines.append(f"{number}. about: {gap.about} · fields: {', '.join(gap.fields)} — {gap.ask}")
    return "\n".join(lines)


def merge_gap_findings(
    findings: Findings,
    found: GapFindings,
    gaps: list[Gap],
    sources: list[SourceCreate],
    first_id: int,
    existing: Iterable[Claim] = (),
) -> GapMerge:
    """Add round-2 statements to the findings and number them as new claims (C{first_id} …).
    A statement must name a gap from the brief, its `about` and one of that gap's fields; anything else is
    dropped with a note. Also dropped: statements already known (same text), statements that repeat the
    numbers of an existing claim on the same topic (live run: the same IMARC figure came back reworded), and
    research-firm figures offered for an "official figure" gap."""
    figures = {(c.subject, c.section, frozenset(numbers_in(c.text))) for c in existing if numbers_in(c.text)}
    primary = primary_hosts(findings)
    retrieved = {url_key(s.url): s.url for s in sources}
    known = {" ".join(t.lower().split()) for t in _all_texts(findings)}
    players = {p.name: p for p in competitors_of(findings)}
    market = isinstance(findings, MarketFindings)
    company_name = None if market else findings.company.name  # type: ignore[union-attr]
    notes: list[str] = []
    claims: list[Claim] = []
    updates: dict[str, dict[str, list[SourcedText]]] = {}
    websites: dict[str, str] = {}
    for item in found.statements:
        gap = gaps[item.gap - 1] if 1 <= item.gap <= len(gaps) else None
        if gap is None or item.field not in gap.fields:
            notes.append(f"Second round: ignored a statement outside the brief ({item.field}: {item.statement.text})")
            continue
        text_key = " ".join(item.statement.text.lower().split())
        if text_key in known or NOT_PUBLIC.search(item.statement.text):
            continue
        known.add(text_key)
        if gap.about in players:
            player = players[gap.about]
            name = player.name
            section, label = f"competitor.{item.field}", dict(COMPETITOR_FIELDS)[item.field]
            if item.website and not player.website and site_root(item.website):
                websites[name] = site_root(item.website)  # type: ignore[assignment]
        elif item.field in ("trends", "industry_context"):
            name, section = INDUSTRY_SUBJECT, "industry"
            label = "Market trends" if market else "Industry context"
        elif market:
            name = findings.market_name  # type: ignore[union-attr]
            section, label = f"market.{item.field}", dict(MARKET_FIELDS)[item.field]
        else:
            name = company_name  # type: ignore[assignment]
            section, label = f"company.{item.field}", dict(COMPANY_FIELDS)[item.field]
        urls = item.statement.source_urls
        if gap.key.startswith("official:") and any(is_research_firm(u) for u in urls):
            if not any(is_primary_source(u, primary) for u in urls):
                notes.append(
                    f"Second round: ignored a research-firm figure offered as official ({item.statement.text})"
                )
                continue
        numbers = frozenset(numbers_in(item.statement.text))
        if numbers and (name, section, numbers) in figures:
            notes.append(f"Second round: ignored a repeat of an existing figure ({item.statement.text})")
            continue
        updates.setdefault(name, {}).setdefault(item.field, []).append(item.statement)
        claims.append(build_claim(f"C{first_id + len(claims)}", name, section, label, item.statement, retrieved))
    return GapMerge(findings=_with_updates(findings, updates, websites), claims=claims, notes=notes)


def _all_texts(findings: Findings) -> list[str]:
    texts: list[str] = []

    def collect(model: object) -> None:
        for name in type(model).model_fields:  # type: ignore[attr-defined]
            value = getattr(model, name)
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, SourcedText):
                    texts.append(item.text)

    collect(findings.company if isinstance(findings, ResearchFindings) else findings)
    for player in competitors_of(findings):
        collect(player)
    return texts


def _add(model, field_name: str, items: list[SourcedText]):  # type: ignore[no-untyped-def]
    current = getattr(model, field_name)
    if isinstance(current, list):
        return model.model_copy(update={field_name: [*current, *items]})
    return model.model_copy(update={field_name: current or items[0]})  # single field: keep an existing one


def _with_updates(
    findings: Findings, updates: dict[str, dict[str, list[SourcedText]]], websites: dict[str, str]
) -> Findings:
    players: list[Competitor] = []
    for player in competitors_of(findings):
        for field_name, items in updates.get(player.name, {}).items():
            player = _add(player, field_name, items)
        if websites.get(player.name):
            player = player.model_copy(update={"website": websites[player.name]})
        players.append(player)
    findings = with_competitors(findings, players)
    industry = updates.get(INDUSTRY_SUBJECT, {})
    if isinstance(findings, MarketFindings):
        for field_name, items in updates.get(findings.market_name, {}).items():
            findings = _add(findings, field_name, items)
        if industry.get("trends"):
            findings = _add(findings, "trends", industry["trends"])
        return findings
    company = findings.company
    for field_name, items in updates.get(company.name, {}).items():
        company = _add(company, field_name, items)
    findings = findings.model_copy(update={"company": company})
    if industry.get("industry_context"):
        findings = _add(findings, "industry_context", industry["industry_context"])
    return findings
