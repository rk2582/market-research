"""Claims: the Researcher's statements, numbered C1, C2 … so later agents can cite them.

Also the checks done in CODE (free, exact) before and after the Fact-Checker:
- a claim whose cited pages were never retrieved is `unsupported` without asking any LLM;
- every claim gets exactly one verdict, even if the Fact-Checker skips it;
- a 'supported' claim that names a year its sources never mention is cut to 'partially_supported'
  (the model sometimes attaches the current year to old news);
- `contradicted` claims are removed before analysis (the gate);
- the company's own brands are not competitors (Instagram is not a competitor of Meta);
- each competitor claim also gets the competitor's own homepage as a source, kept only when the
  Fact-Checker says that page supports it;
- with a list the user confirmed (M12), only those competitors are kept, in the user's order, and any the
  Researcher could not profile are reported as missing;
- market reports (M13): a claim that rests on a market-research firm's summary page (IMARC, Mordor …) is an
  ESTIMATE and labelled so, even when a blog repeats the same number; a market player needs at least two
  sourced statements to be profiled;
- M14: each checked claim keeps the year its supporting page states (from the Fact-Checker, else from a
  /2018/ in the URL); a trend, price or recent-news claim whose source is more than 3 years old is labelled.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from schemas.findings import ClaimVerdict, CompanyProfile, Competitor, MarketFindings, ResearchFindings, SourcedText
from schemas.report import CheckedClaim, Claim, ValidationSummary
from schemas.research import SourceCreate
from workflow.source_harvest import url_key

COMPANY_FIELDS: tuple[tuple[str, str], ...] = (
    ("identity_note", "Identity"),
    ("description", "Description"),
    ("industry", "Industry"),
    ("products_services", "Products and services"),
    ("customer_segments", "Customer segments"),
    ("geographic_presence", "Geography"),
    ("business_model", "Business model"),
    ("pricing", "Pricing"),
    ("funding", "Funding"),
    ("recent_developments", "Recent developments"),
    ("positioning_usp", "Positioning"),
)
COMPETITOR_FIELDS: tuple[tuple[str, str], ...] = (
    ("description", "Description"),
    ("offerings", "Offerings"),
    ("pricing", "Pricing"),
    ("target_segments", "Target customers"),
    ("positioning", "Positioning"),
)
# Market-entry reports (M13): the market's facts, shown where a company report shows the company's.
MARKET_FIELDS: tuple[tuple[str, str], ...] = (
    ("scope_note", "Scope"),
    ("market_size", "Market size"),
    ("growth", "Growth"),
    ("customers_demand", "Customers and demand"),
    ("prices", "Prices"),
    ("supply_chain", "Supply chain"),
    ("regulation", "Licences and rules"),
    ("costs_margins", "Costs and margins"),
    ("barriers", "Entry barriers"),
)
INDUSTRY_SUBJECT = "Industry"
Findings = ResearchFindings | MarketFindings

# Firms that sell market-size reports. Their free summary pages give one firm's estimate (often for a broader
# market than the title says), and different firms publish very different numbers for the same market.
RESEARCH_FIRM_SITES = (
    "imarcgroup.com",
    "mordorintelligence.com",
    "grandviewresearch.com",
    "marketsandmarkets.com",
    "fortunebusinessinsights.com",
    "expertmarketresearch.com",
    "researchandmarkets.com",
    "alliedmarketresearch.com",
    "precedenceresearch.com",
    "futuremarketinsights.com",
    "persistencemarketresearch.com",
    "transparencymarketresearch.com",
    "verifiedmarketresearch.com",
    "marketresearchfuture.com",
    "techsciresearch.com",
    "kenresearch.com",
    "6wresearch.com",
    "blueweaveconsulting.com",
    "custommarketinsights.com",
    "databridgemarketresearch.com",
    "coherentmarketinsights.com",
    "skyquestt.com",
    "sphericalinsights.com",
    "zionmarketresearch.com",
    "polarismarketresearch.com",
    "maximizemarketresearch.com",
    "straitsresearch.com",
    "renub.com",
    "statista.com",
)
MIN_PLAYER_FACTS = 2
# A statement that only says something is NOT public is a gap in our research, not a fact (live run: "Publicly
# available official data on start-up costs … is not disclosed by government"). Such statements never become
# claims, so the topic shows as "Not found in public sources". Narrow on purpose: "not available in Kerala" is a fact.
NOT_PUBLIC = re.compile(
    r"\b(not (publicly|officially) (available|disclosed|reported)|no (publicly available|public|official)"
    r" (data|information|figures?)|could not be found|(is|are|was|were) not (publicly )?disclosed|not disclosed by"
    r"|not found in (public|available) sources)\b",
    re.IGNORECASE,
)
# M14: claims that go stale — an old page is no evidence of how things are today.
STALE_LABELS = frozenset({"Recent developments", "Pricing", "Prices", "Market trends", "Industry context"})
OLD_SOURCE_YEARS = 3
_URL_YEAR = re.compile(r"/((?:19|20)\d{2})/")


def url_year(url: str) -> int | None:
    """'https://site.com/news/2018/10/08/…' → 2018."""
    match = _URL_YEAR.search(urlsplit(url).path)
    return int(match.group(1)) if match else None


def current_year() -> int:
    return datetime.now(UTC).year


def old_source_year(claim: CheckedClaim, now_year: int) -> int | None:
    """The source year when a claim that goes stale rests on a page more than 3 years old."""
    year = claim.source_year
    if claim.label in STALE_LABELS and year is not None and now_year - year > OLD_SOURCE_YEARS:
        return year
    return None


def is_research_firm(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == site or host.endswith(f".{site}") for site in RESEARCH_FIRM_SITES)


_GOVERNMENT_HOST = re.compile(r"(^|\.)(gov|nic|gob|gouv|govt)(\.[a-z]{2,3})?$|\.gc\.ca$|(^|\.)europa\.eu$|\.int$")


def is_primary_source(url: str, primary: Iterable[str] = ()) -> bool:
    """A government site, or the company's / a player's own website (hosts in `primary`)."""
    host = _host(url)
    return bool(_GOVERNMENT_HOST.search(host)) or host in set(primary)


def primary_hosts(findings: Findings) -> frozenset[str]:
    """Hosts of the company's and the competitors'/players' own websites."""
    sites = [c.website for c in competitors_of(findings)]
    if isinstance(findings, ResearchFindings):
        sites.append(findings.company.website)
    return frozenset(_host(s) for s in sites if s)


def is_estimate(claim: Claim, primary: Iterable[str] = ()) -> bool:
    """A research-firm figure: some source is a market-research firm's page and none is primary (a government
    site or the company's own website). Blogs and news often copy the firm's number word for word (live run:
    a blog repeating IMARC's figure hid it), so they don't make it official; the company's own site does."""
    primary = set(primary)
    return any(is_research_firm(u) for u in claim.source_urls) and not any(
        is_primary_source(u, primary) for u in claim.source_urls
    )


def drop_thin_players(
    findings: MarketFindings, claims: list[CheckedClaim]
) -> tuple[MarketFindings, list[CheckedClaim], list[str]]:
    """A market player is profiled only with at least MIN_PLAYER_FACTS confirmed claims; one vague line
    ('X is a known player') tells a newcomer nothing. Runs AFTER the second research round (M14), so that
    round can research thin players first. Returns the findings, the claims without the dropped players'
    claims, and notes."""
    confirmed: dict[str, int] = {}
    for claim in claims:
        if claim.section.startswith("competitor.") and claim.verdict in ("supported", "partially_supported"):
            confirmed[claim.subject] = confirmed.get(claim.subject, 0) + 1
    kept: list[Competitor] = []
    dropped: set[str] = set()
    notes: list[str] = []
    for player in findings.players:
        if confirmed.get(player.name, 0) >= MIN_PLAYER_FACTS:
            kept.append(player)
        else:
            dropped.add(player.name)
            notes.append(f"Left out player {player.name}: fewer than {MIN_PLAYER_FACTS} confirmed facts found.")
    remaining = [c for c in claims if not (c.section.startswith("competitor.") and c.subject in dropped)]
    return findings.model_copy(update={"players": kept}), remaining, notes


def merge_competitor(pick: Competitor, found: Competitor) -> Competitor:
    """M15: the lead's pick (name, relation, maybe a website and one line) + its own researcher's profile.
    The pick's name and relation are kept (they match the confirmed list); the profile's facts are added."""
    merged: dict[str, Any] = {}
    for name in ("offerings", "target_segments"):
        merged[name] = [*getattr(pick, name), *getattr(found, name)]
    for name in ("pricing", "positioning"):
        merged[name] = getattr(found, name) or getattr(pick, name)
    merged["description"] = found.description if found.description.source_urls else pick.description
    merged["website"] = site_root(found.website) or pick.website
    return pick.model_copy(update=merged)


def competitors_of(findings: Findings) -> list[Competitor]:
    """Competitors of a company, or the main players of a market."""
    return findings.players if isinstance(findings, MarketFindings) else findings.competitors


def with_competitors(findings: Findings, competitors: list[Competitor]) -> Findings:
    key = "players" if isinstance(findings, MarketFindings) else "competitors"
    return findings.model_copy(update={key: competitors})


_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def site_root(url: str | None) -> str | None:
    """'https://www.notion.com/enterprise' → 'https://www.notion.com' (the Researcher sometimes
    returns a sub-page as the company website)."""
    if not url:
        return None
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc.lower()}"


def _items(value: SourcedText | list[SourcedText] | None) -> list[SourcedText]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def dedupe_findings(findings: Findings) -> Findings:
    """The model sometimes repeats competitors or statements (seen live: every competitor twice).
    Keep the first competitor per name and the first copy of each statement."""

    def unique(items: list[SourcedText]) -> list[SourcedText]:
        seen: set[str] = set()
        kept: list[SourcedText] = []
        for item in items:
            key = " ".join(item.text.lower().split())
            if key not in seen:
                seen.add(key)
                kept.append(item)
        return kept

    def clean_lists(model: CompanyProfile | Competitor | MarketFindings) -> dict[str, list[SourcedText]]:
        return {
            name: unique(value)
            for name in type(model).model_fields
            if isinstance(value := getattr(model, name), list) and all(isinstance(v, SourcedText) for v in value)
        }

    competitors: list[Competitor] = []
    names: set[str] = set()
    for comp in competitors_of(findings):
        key = comp.name.strip().lower()
        if key not in names:
            names.add(key)
            competitors.append(comp.model_copy(update=clean_lists(comp)))
    if isinstance(findings, MarketFindings):  # every list field (incl. trends), then the players
        return with_competitors(findings.model_copy(update=clean_lists(findings)), competitors)
    return findings.model_copy(
        update={
            "company": findings.company.model_copy(update=clean_lists(findings.company)),
            "competitors": competitors,
            "industry_context": unique(findings.industry_context),
        }
    )


def name_key(name: str) -> str:
    """'Freshsales (Freshworks CRM)' → 'freshsales'; 'Notion Labs, Inc.' → 'notionlabsinc'."""
    return re.sub(r"[^a-z0-9]", "", name.split("(", 1)[0].lower())


def host_of(url: str | None) -> str | None:
    root = site_root(url)
    return root.split("://", 1)[1].removeprefix("www.") if root else None


def _words(name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", name.split("(", 1)[0].lower())


def same_company(name_a: str, site_a: str | None, name_b: str, site_b: str | None) -> bool:
    """Loose match between a name the user confirmed and one the Researcher returned: same website, or
    one name is the other plus extra words ('HubSpot' = 'HubSpot CRM', but 'Coda' ≠ 'Codacy')."""
    host_a, host_b = host_of(site_a), host_of(site_b)
    if host_a and host_b and host_a == host_b:
        return True
    a, b = _words(name_a), _words(name_b)
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return longer[: len(shorter)] == shorter


def apply_confirmed_competitors(
    findings: ResearchFindings, confirmed: list[dict[str, Any]]
) -> tuple[ResearchFindings, list[str], list[str]]:
    """Keep exactly the confirmed competitors, in the user's order. Returns (findings, notes, missing names)."""
    remaining = list(findings.competitors)
    kept: list[Competitor] = []
    missing: list[str] = []
    for wanted in confirmed:
        match = next(
            (c for c in remaining if same_company(wanted["name"], wanted.get("website"), c.name, c.website)), None
        )
        if match is None:
            missing.append(wanted["name"])
            continue
        remaining.remove(match)
        if not match.website and wanted.get("website"):
            match = match.model_copy(update={"website": site_root(wanted["website"])})
        kept.append(match)
    notes = [f"Removed competitor {c.name}: it was not on the list you confirmed." for c in remaining]
    notes += [f"Not enough reliable public information was found about {name}." for name in missing]
    return findings.model_copy(update={"competitors": kept}), notes, missing


def _host(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host.removeprefix("www.")


def _short_names(name: str) -> list[str]:
    """'Meta Platforms, Inc. (formerly Facebook, Inc.)' → ['Meta Platforms', 'Meta']."""
    core = re.split(r"[,(]", name, maxsplit=1)[0].strip()
    names = [core] if core else []
    first = core.split()[0] if core.split() else ""
    if first and first != core and len(first) >= 3:
        names.append(first)
    return names


def _starts_with_name(text: str, name: str) -> bool:
    return bool(re.match(rf"\s*(the\s+)?{re.escape(name)}\b", text, re.IGNORECASE))


def own_brand_reason(company: CompanyProfile, competitor: Competitor) -> str | None:
    """Why a 'competitor' is really part of the target company, or None."""
    if competitor.name.strip().lower() == company.name.strip().lower():
        return "it is the company itself"
    if competitor.website and company.website and _host(competitor.website) == _host(company.website):
        return "it has the same website as the company"
    owners = "|".join(re.escape(n) for n in _short_names(company.name))
    if owners and re.search(
        rf"\b(owned by|subsidiary of|part of|a division of|a brand of|acquired by)\s+(the\s+)?({owners})\b",
        competitor.description.text,
        re.IGNORECASE,
    ):
        return "its description says the company owns it"
    if any(_starts_with_name(item.text, competitor.name) for item in company.products_services):
        return "it is listed as one of the company's own products"
    return None


def drop_own_brands(findings: ResearchFindings) -> tuple[ResearchFindings, list[str]]:
    """Remove 'competitors' the company owns (seen live: Instagram listed as a competitor of Meta)."""
    kept: list[Competitor] = []
    notes: list[str] = []
    for competitor in findings.competitors:
        reason = own_brand_reason(findings.company, competitor)
        if reason:
            notes.append(f"Removed competitor {competitor.name}: {reason}.")
        else:
            kept.append(competitor)
    return findings.model_copy(update={"competitors": kept}), notes


def competitor_homepages_to_fetch(findings: Findings, sources: Iterable[SourceCreate]) -> list[str]:
    """Competitor homepages that were not retrieved during research."""
    have = {_host(s.url) for s in sources if urlsplit(s.url).path in ("", "/")}
    return [c.website for c in competitors_of(findings) if c.website and _host(c.website) not in have]


def add_competitor_homepages(claims: list[Claim], findings: Findings, sources: Iterable[SourceCreate]) -> list[Claim]:
    """Give each competitor claim its competitor's homepage as an extra source (when we have that page).
    The Researcher often cites a third-party list; the competitor's own site is better evidence."""
    homepage_by_host = {_host(s.url): s.url for s in sources if urlsplit(s.url).path in ("", "/")}
    homepage_for = {c.name: homepage_by_host.get(_host(c.website)) for c in competitors_of(findings) if c.website}
    out: list[Claim] = []
    for claim in claims:
        home = homepage_for.get(claim.subject) if claim.section.startswith("competitor.") else None
        if home and home not in claim.source_urls:
            claim = claim.model_copy(update={"source_urls": [*claim.source_urls, home], "code_added_urls": [home]})
        out.append(claim)
    return out


def unread_cited_urls(findings: Findings, sources: Iterable[SourceCreate]) -> list[str]:
    """URLs the findings cite that no tool call retrieved, most-cited first."""
    counts: dict[str, int] = {}
    for claim in extract_claims(findings, sources):
        for url in claim.cited_but_not_retrieved:
            counts[url] = counts.get(url, 0) + 1
    return sorted(counts, key=lambda u: -counts[u])


def build_claim(
    claim_id: str, subject: str, section: str, label: str, statement: SourcedText, retrieved: dict[str, str]
) -> Claim:
    """One numbered claim; `retrieved` maps url_key → URL of every page actually retrieved."""
    kept: list[str] = []
    missing: list[str] = []
    for url in statement.source_urls:
        source_url = retrieved.get(url_key(url))
        if source_url is None:
            missing.append(url)
        elif source_url not in kept:
            kept.append(source_url)
    return Claim(
        id=claim_id,
        subject=subject,
        section=section,
        label=label,
        text=statement.text.strip(),
        kind=statement.kind,
        source_urls=kept,
        cited_but_not_retrieved=missing,
    )


def extract_claims(findings: Findings, sources: Iterable[SourceCreate]) -> list[Claim]:
    """Number every statement and split its URLs into retrieved (kept) and never-retrieved."""
    retrieved = {url_key(s.url): s.url for s in sources}
    claims: list[Claim] = []

    def add(subject: str, section: str, label: str, statement: SourcedText) -> None:
        if NOT_PUBLIC.search(statement.text):
            return  # a gap, not a fact
        claims.append(build_claim(f"C{len(claims) + 1}", subject, section, label, statement, retrieved))

    if isinstance(findings, MarketFindings):
        for field, label in MARKET_FIELDS:
            for statement in _items(getattr(findings, field)):
                add(findings.market_name, f"market.{field}", label, statement)
    else:
        company: CompanyProfile = findings.company
        for field, label in COMPANY_FIELDS:
            for statement in _items(getattr(company, field)):
                add(company.name, f"company.{field}", label, statement)
    competitor: Competitor
    for competitor in competitors_of(findings):
        for field, label in COMPETITOR_FIELDS:
            for statement in _items(getattr(competitor, field)):
                add(competitor.name, f"competitor.{field}", label, statement)
    context = findings.trends if isinstance(findings, MarketFindings) else findings.industry_context
    label = "Market trends" if isinstance(findings, MarketFindings) else "Industry context"
    for statement in context:
        add(INDUSTRY_SUBJECT, "industry", label, statement)
    return claims


def batches(claims: list[Claim], size: int) -> list[list[Claim]]:
    return [claims[i : i + size] for i in range(0, len(claims), size)]


def needs_fact_check(claim: Claim) -> bool:
    return bool(claim.source_urls)


def code_verdict(claim: Claim) -> CheckedClaim:
    """Verdict for a claim with no retrieved source — decided in code, no LLM call."""
    if claim.cited_but_not_retrieved:
        reason = "Cited pages were never retrieved in this run."
    else:
        reason = "No source was given for this claim."
    return CheckedClaim(**claim.model_dump(), verdict="unsupported", confidence="low", reason=reason, checked_by="code")


def years_missing_from_sources(claim: Claim, sources: Iterable[SourceCreate]) -> list[str]:
    """Years named in the claim that appear nowhere in its cited sources (url, title or excerpt)."""
    cited = {url_key(u) for u in claim.source_urls}
    text = " ".join(f"{s.url} {s.title or ''} {s.excerpt or ''}" for s in sources if url_key(s.url) in cited)
    return sorted({y for y in _YEAR.findall(claim.text) if y not in text})


def merge_verdicts(
    claims: list[Claim], verdicts: Iterable[ClaimVerdict], sources: Iterable[SourceCreate] = ()
) -> list[CheckedClaim]:
    """Exactly one verdict per claim, in claim order. Unknown ids from the model are ignored."""
    by_id = {v.claim_id.strip(): v for v in verdicts}
    sources = list(sources)
    checked: list[CheckedClaim] = []
    for claim in claims:
        if not needs_fact_check(claim):
            checked.append(code_verdict(claim))
            continue
        verdict = by_id.get(claim.id)
        if verdict is None:
            checked.append(
                CheckedClaim(
                    **claim.model_dump(),
                    verdict="unsupported",
                    confidence="low",
                    reason="Not assessed by the fact-checker.",
                    checked_by="code",
                )
            )
            continue
        verdict_value, reason, checked_by = verdict.verdict, verdict.reason.strip(), "fact_checker"
        claim = claim.model_copy(update={"source_urls": _credited_sources(claim, verdict)})
        url_years = [y for u in claim.source_urls if (y := url_year(u)) is not None]
        source_year = verdict.source_year or (max(url_years) if url_years else None)
        missing_years = years_missing_from_sources(claim, sources) if sources else []
        if verdict_value == "supported" and missing_years:
            verdict_value = "partially_supported"
            reason = f"Year {', '.join(missing_years)} not found in the cited sources. {reason}"
            checked_by = "code"
        checked.append(
            CheckedClaim(
                **claim.model_dump(),
                verdict=verdict_value,
                confidence=verdict.confidence,
                reason=reason,
                checked_by=checked_by,
                source_year=source_year,
            )
        )
    return checked


def _credited_sources(claim: Claim, verdict: ClaimVerdict) -> list[str]:
    """Keep the sources the Fact-Checker says hold the evidence. A homepage added by code stays only
    if the Fact-Checker named it."""
    named = {url_key(u) for u in verdict.supporting_urls}
    if verdict.verdict in ("supported", "partially_supported"):
        credited = [u for u in claim.source_urls if url_key(u) in named]
        if credited:
            return credited
    added = {url_key(u) for u in claim.code_added_urls}
    return [u for u in claim.source_urls if url_key(u) not in added]


def gate(checked: list[CheckedClaim]) -> tuple[list[CheckedClaim], ValidationSummary]:
    """Remove contradicted claims; count verdicts; write warnings people should see in the report."""
    summary = ValidationSummary(claims_total=len(checked))
    kept: list[CheckedClaim] = []
    for claim in checked:
        match claim.verdict:
            case "supported":
                summary.supported += 1
            case "partially_supported":
                summary.partially_supported += 1
            case "unsupported":
                summary.unsupported += 1
            case "contradicted":
                summary.contradicted += 1
                summary.warnings.append(f"Removed {claim.id} ({claim.subject}): {claim.text} — {claim.reason}")
                continue
        kept.append(claim)
    never_retrieved = sum(1 for c in checked if c.cited_but_not_retrieved)
    if never_retrieved:
        summary.warnings.append(f"{never_retrieved} claim(s) cited pages that were never retrieved.")
    return kept, summary
