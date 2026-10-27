"""Builds the final report in CODE from the agents' structured outputs.

The LLMs never re-type tables, SWOT items or references here, so nothing can be lost or invented
at this stage. This module also enforces the evidence rules:
- insights and recommendations must cite at least one known, non-contradicted claim (else dropped);
- an insight labelled 'fact' that rests only on unsupported claims is downgraded to 'interpretation';
- an insight labelled 'fact' that hedges (could, may, might, likely …) is shown as 'interpretation';
- [C12] citations in prose become source numbers like [3][7]; unknown ids are removed and repeats merged;
- references list only the sources some claim cites, numbered 1..n in retrieval order;
- insights and recommendations with no retrieved source behind them are dropped;
- insights and recommendations built on missing data ("no evidence was found …") are dropped — a gap in
  our research is not a finding about the company;
- evidence ids (F2, C7) and other stray brackets are removed from prose; 'C4-C6' ranges are understood;
- comparison rows where fewer than two companies have sourced data are dropped, and so are competitor
  columns with no sourced cell at all; verdict words the model writes into cells ("Unsupported.") are removed;
- opportunities and risks are judgements, so they are never labelled 'fact';
- a key figure (a number for charts) is kept only if that exact number appears in a cited claim the
  fact-checker supported or partly supported — no chart shows a number we can't trace to a source;
- market-entry reports (M13): each five-forces rating needs known claims with a retrieved source, like
  insights; signals for/against follow the insight rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from schemas.findings import (
    AnalysisFindings,
    Insight,
    KeyFigure,
    MarketAnalysisFindings,
    MarketFindings,
    ReportNarrative,
    StrategyRecommendations,
    Swot,
)
from schemas.report import (
    REPORT_SECTIONS,
    AnalysisOut,
    CheckedClaim,
    CompanyOverview,
    ComparisonCellOut,
    ComparisonRowOut,
    CompetitorProfile,
    FactGroup,
    ForceOut,
    IndustryOverview,
    InsightOut,
    KeyFigureOut,
    MarketScopeReport,
    MarketSection,
    RecommendationOut,
    Reference,
    Report,
    ReportClaim,
    ReportMeta,
    SecondRoundOut,
    StepUsageOut,
    SwotOut,
    ValidationSummary,
)
from schemas.research import SourceCreate
from workflow.claims import (
    COMPANY_FIELDS,
    COMPETITOR_FIELDS,
    MARKET_FIELDS,
    Findings,
    competitors_of,
    current_year,
    is_estimate,
    old_source_year,
    primary_hosts,
    site_root,
)
from workflow.source_harvest import url_key

_ID = r"C\d+(?:\s*[-–]\s*C?\d+)?"  # C4, or a range C4-C9 / C4-9
_CITATION = re.compile(rf"\[(\s*{_ID}\s*(?:[,;]\s*{_ID}\s*)*)\]")
_STRAY_BRACKET = re.compile(r"\s*\[[A-Z]\w*(?:\s*[,;]\s*[A-Z]\w*)*\]")  # [Recommendations], [F2, F3]
# "(F2, F14)", "(see C4)", "(Implied by F13, F10)" in a rationale or step — a few words, then ids, nothing else
_ID_LIST = re.compile(r"\s*\((?:[A-Za-z][A-Za-z ]{0,30}\s)?[CF]\d+(?:\s*(?:[,;]|and)\s*[CF]\d+)*\)")
_GAP_TALK = re.compile(
    r"\b(no (current )?evidence|not (publicly )?(available|found|disclosed)|no (public )?(data|information)|"
    r"could not be found|lack of (public )?(data|information))\b",
    re.IGNORECASE,
)
_REF_RUN = re.compile(r"(?:\[\d+\])+")
_CELL_VERDICT = re.compile(
    r"\s*\(?\b(unsupported|unconfirmed|partially supported|partly verified|contradicted)\b\)?\.?\s*$", re.IGNORECASE
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
MAX_KEY_FIGURES = 8
_JUDGEMENT_GROUPS = {"SWOT opportunity", "opportunity", "risk"}  # never 'fact'
_HEDGE = re.compile(r"\b(could|may|might|likely|potentially|possibly)\b")  # lower-case only: not the month May


class Evidence:
    """Lookups shared by the assembler: claims by id and source reference numbers by URL."""

    def __init__(
        self, claims: list[CheckedClaim], sources: list[SourceCreate], primary: frozenset[str] = frozenset()
    ) -> None:
        self.claims = {c.id: c for c in claims}
        self.primary = primary  # hosts of the company's / players' own websites (M14 estimate rule)
        cited_keys = {url_key(u) for c in claims for u in c.source_urls}
        # Only sources that some claim cites get a number (retrieved-but-unused pages are left out).
        self.cited_sources = [s for s in sources if url_key(s.url) in cited_keys]
        self.ref_by_key = {url_key(s.url): i for i, s in enumerate(self.cited_sources, start=1)}

    def refs_for_claims(self, claim_ids: list[str]) -> list[int]:
        refs: set[int] = set()
        for cid in claim_ids:
            claim = self.claims.get(cid)
            if claim:
                refs.update(self.ref_by_key[url_key(u)] for u in claim.source_urls if url_key(u) in self.ref_by_key)
        return sorted(refs)

    def known(self, claim_ids: list[str]) -> list[str]:
        seen: list[str] = []
        for cid in (c.strip() for c in claim_ids):
            if cid in self.claims and cid not in seen:
                seen.append(cid)
        return seen

    def report_claim(self, claim: CheckedClaim) -> ReportClaim:
        return ReportClaim(
            id=claim.id,
            text=claim.text,
            kind=claim.kind,
            verdict=claim.verdict,
            confidence=claim.confidence,
            refs=self.refs_for_claims([claim.id]),
            estimate=is_estimate(claim, self.primary),
            old_source_year=old_source_year(claim, current_year()),
        )

    def cite(self, text: str) -> str:
        """'… in 2021 [C12, C3].' → '… in 2021 [2][9].' (unknown ids dropped)."""

        def replace(match: re.Match[str]) -> str:
            ids = [cid for part in re.split(r"[,;]", match.group(1)) for cid in _expand(part.strip())]
            refs = self.refs_for_claims(self.known(ids))
            return "".join(f"[{r}]" for r in refs)

        def merge(match: re.Match[str]) -> str:  # "[1][2][1][1]" → "[1][2]"
            numbers = sorted({int(n) for n in re.findall(r"\d+", match.group(0))})
            return "".join(f"[{n}]" for n in numbers)

        cited = _REF_RUN.sub(merge, _STRAY_BRACKET.sub("", _CITATION.sub(replace, text)))
        return re.sub(r"\s+([.,;:])", r"\1", cited).strip()


def _expand(token: str) -> list[str]:
    """'C4-C6' → ['C4', 'C5', 'C6']; 'C7' → ['C7']. Silly ranges (>50 ids) are ignored."""
    match = re.fullmatch(r"C(\d+)\s*[-–]\s*C?(\d+)", token)
    if not match:
        return [token]
    start, end = int(match.group(1)), int(match.group(2))
    return [f"C{n}" for n in range(start, end + 1)] if 0 <= end - start <= 50 else []


def strip_ids(text: str) -> str:
    """Remove evidence-id lists like '(F2, F14)' that mean nothing to a reader."""
    return re.sub(r"\s+([.,;:])", r"\1", _ID_LIST.sub("", text)).strip()


# ---------------------------------------------------------------------------
# Analysis and recommendations: verify evidence, number insights
# ---------------------------------------------------------------------------


def process_analysis(
    raw: AnalysisFindings,
    evidence: Evidence,
    *,
    swot_groups: tuple[str, str, str, str] = ("strength", "weakness", "SWOT opportunity", "threat"),
) -> tuple[AnalysisOut, list[str]]:
    warnings: list[str] = []
    counter = 0

    def convert(items: list[Insight], group: str) -> list[InsightOut]:
        nonlocal counter
        out: list[InsightOut] = []
        for item in items:
            claim_ids = evidence.known(item.evidence_claim_ids)
            if _GAP_TALK.search(item.text):
                warnings.append(f"Dropped {group} insight based on missing data: {item.text}")
                continue
            if not claim_ids:
                warnings.append(f"Dropped {group} insight with no valid evidence: {item.text}")
                continue
            kind = item.kind
            if kind == "fact" and all(evidence.claims[c].verdict == "unsupported" for c in claim_ids):
                kind = "interpretation"
                warnings.append(f"'{item.text}' rests only on unsupported claims; shown as interpretation.")
            elif kind == "fact" and (_HEDGE.search(item.text) or group in _JUDGEMENT_GROUPS):
                kind = "interpretation"  # a hedged sentence, opportunity or risk is a judgement, not a sourced fact
            refs = evidence.refs_for_claims(claim_ids)
            if not refs:
                warnings.append(f"Dropped {group} insight with no retrieved source: {item.text}")
                continue
            counter += 1
            out.append(
                InsightOut(
                    id=f"F{counter}",
                    text=item.text.strip(),
                    kind=kind,
                    claim_ids=claim_ids,
                    refs=refs,
                )
            )
        return out

    swot = SwotOut(
        strengths=convert(raw.swot.strengths, swot_groups[0]),
        weaknesses=convert(raw.swot.weaknesses, swot_groups[1]),
        opportunities=convert(raw.swot.opportunities, swot_groups[2]),
        threats=convert(raw.swot.threats, swot_groups[3]),
    )
    rows = [
        ComparisonRowOut(
            dimension=row.dimension.strip(),
            cells=[
                ComparisonCellOut(
                    company=cell.company.strip(),
                    value=_CELL_VERDICT.sub("", cell.value).strip() or cell.value.strip(),
                    refs=evidence.refs_for_claims(evidence.known(cell.claim_ids)),
                )
                for cell in row.cells
            ],
        )
        for row in raw.comparison
    ]
    comparison = [row for row in rows if sum(1 for cell in row.cells if cell.refs) >= 2]
    warnings += [
        f"Dropped comparison row '{row.dimension}': fewer than two companies have sourced data."
        for row in rows
        if row not in comparison
    ]
    comparison, empty = _drop_empty_columns(comparison)
    warnings += [f"Dropped {name} from the comparison table: no sourced data." for name in empty]
    key_figures, figure_warnings = process_key_figures(raw.key_figures, evidence)
    warnings += figure_warnings
    analysis = AnalysisOut(
        comparison=comparison,
        swot=swot,
        trends=convert(raw.trends, "trend"),
        opportunities=convert(raw.opportunities, "opportunity"),
        risks=convert(raw.risks, "risk"),
        data_gaps=[g.strip() for g in raw.data_gaps if g.strip()],
        key_figures=key_figures,
    )
    return analysis, warnings


FORCE_ORDER = ("rivalry", "entry_barriers", "supplier_power", "buyer_power", "substitutes")


def process_market_analysis(
    raw: MarketAnalysisFindings, evidence: Evidence
) -> tuple[AnalysisOut, list[ForceOut], list[str]]:
    """Market analysis: signals for/against go through the insight rules (carried in the SWOT's strengths and
    weaknesses slots until the report is assembled); each force rating needs real, sourced evidence."""
    mapped = AnalysisFindings(
        comparison=raw.comparison,
        swot=Swot(strengths=raw.signals_for, weaknesses=raw.signals_against, opportunities=[], threats=[]),
        trends=raw.trends,
        opportunities=raw.opportunities,
        risks=raw.risks,
        data_gaps=raw.data_gaps,
        key_figures=raw.key_figures,
    )
    analysis, warnings = process_analysis(mapped, evidence, swot_groups=("signal for", "signal against", "-", "-"))
    forces: dict[str, ForceOut] = {}
    for rating in raw.forces:
        claim_ids = evidence.known(rating.evidence_claim_ids)
        refs = evidence.refs_for_claims(claim_ids)
        label = rating.force.replace("_", " ")
        if rating.force in forces:
            warnings.append(f"Dropped a second rating for {label}.")
        elif not claim_ids or not refs or _GAP_TALK.search(rating.reason):
            warnings.append(f"Dropped the {label} rating: no sourced evidence behind it.")
        else:
            forces[rating.force] = ForceOut(
                force=rating.force, rating=rating.rating, reason=rating.reason.strip(), claim_ids=claim_ids, refs=refs
            )
    return analysis, [forces[f] for f in FORCE_ORDER if f in forces], warnings


def numbers_in(text: str) -> set[float]:
    """'$1,861.5 million, up 39%' → {1861.5, 39.0}."""
    return {float(m.replace(",", "")) for m in _NUMBER.findall(text)}


def process_key_figures(raw: list[KeyFigure], evidence: Evidence) -> tuple[list[KeyFigureOut], list[str]]:
    """Keep a figure only when its number is written in a cited claim that the fact-checker backed."""
    kept: list[KeyFigureOut] = []
    warnings: list[str] = []
    for figure in raw:
        name = f"{figure.company} — {figure.label}: {figure.value:g} {figure.unit}"
        backing = [
            cid
            for cid in evidence.known(figure.claim_ids)
            if evidence.claims[cid].verdict in ("supported", "partially_supported")
            and any(abs(n - figure.value) < 1e-9 for n in numbers_in(evidence.claims[cid].text))
        ]
        refs = evidence.refs_for_claims(backing)
        if not backing or not refs:
            warnings.append(f"Dropped key figure {name}: the number is not in a verified claim it cites.")
            continue
        if len(kept) == MAX_KEY_FIGURES:
            warnings.append(f"Dropped key figure {name}: more than {MAX_KEY_FIGURES} figures.")
            continue
        kept.append(
            KeyFigureOut(
                label=figure.label.strip(),
                company=figure.company.strip(),
                value=figure.value,
                unit=figure.unit.strip(),
                year=figure.year,
                claim_ids=backing,
                refs=refs,
                estimate=all(is_estimate(evidence.claims[cid], evidence.primary) for cid in backing),
            )
        )
    return kept, warnings


def _drop_empty_columns(rows: list[ComparisonRowOut]) -> tuple[list[ComparisonRowOut], list[str]]:
    """Remove competitors whose every cell is unsourced (seen live: a Snapchat column of
    'Not publicly available'). The target company (first column) always stays."""
    if not rows or not rows[0].cells:
        return rows, []
    target = rows[0].cells[0].company
    names = list(dict.fromkeys(cell.company for row in rows for cell in row.cells))
    sourced = {cell.company for row in rows for cell in row.cells if cell.refs}
    empty = [n for n in names if n != target and n not in sourced]
    if not empty:
        return rows, []
    kept = [row.model_copy(update={"cells": [c for c in row.cells if c.company not in empty]}) for row in rows]
    return kept, empty


def process_recommendations(
    raw: StrategyRecommendations, analysis: AnalysisOut, evidence: Evidence
) -> tuple[list[RecommendationOut], list[str]]:
    warnings: list[str] = []
    insights = {i.id: i for i in analysis.all_insights()}
    kept: list[tuple[int, RecommendationOut]] = []
    for draft in raw.recommendations:
        evidence_ids: list[str] = []
        claim_ids: list[str] = []
        for eid in (e.strip() for e in draft.evidence_ids):
            if eid in insights and eid not in evidence_ids:
                evidence_ids.append(eid)
                claim_ids.extend(insights[eid].claim_ids)
            elif eid in evidence.claims and eid not in evidence_ids:
                evidence_ids.append(eid)
                claim_ids.append(eid)
        if not evidence_ids:
            warnings.append(f"Dropped recommendation with no valid evidence: {draft.title}")
            continue
        if _GAP_TALK.search(f"{draft.title} {draft.rationale}"):
            warnings.append(f"Dropped recommendation based on missing data: {draft.title}")
            continue
        claim_ids = list(dict.fromkeys(claim_ids))
        refs = evidence.refs_for_claims(claim_ids)
        if not refs:
            warnings.append(f"Dropped recommendation with no retrieved source: {draft.title}")
            continue
        weak = all(evidence.claims[c].verdict == "unsupported" for c in claim_ids)
        kept.append(
            (
                draft.priority,
                RecommendationOut(
                    priority=0,
                    title=draft.title.strip(),
                    rationale=strip_ids(draft.rationale),
                    impact=draft.impact,
                    next_steps=[t for s in draft.next_steps if (t := strip_ids(s))],
                    risks_tradeoffs=[t for r in draft.risks_tradeoffs if (t := strip_ids(r))],
                    evidence_ids=evidence_ids,
                    refs=refs,
                    warning="Based only on claims the fact-checker could not confirm." if weak else None,
                ),
            )
        )
    kept.sort(key=lambda pair: pair[0])
    recommendations = [rec.model_copy(update={"priority": n}) for n, (_, rec) in enumerate(kept, start=1)]
    if len(recommendations) < 3:
        warnings.append(f"Only {len(recommendations)} recommendation(s) had enough evidence (target: 3-7).")
    return recommendations, warnings


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------


@dataclass
class ReportInputs:
    query: str
    findings: Findings
    sources: list[SourceCreate]
    claims: list[CheckedClaim]  # after the gate (no contradicted claims)
    validation: ValidationSummary
    analysis: AnalysisOut | None = None
    recommendations: list[RecommendationOut] | None = None
    narrative: ReportNarrative | None = None
    usage: list[StepUsageOut] = field(default_factory=list)
    step_errors: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    agent_versions: dict[str, str] = field(default_factory=dict)
    competitors_confirmed: bool = False
    missing_competitors: list[str] = field(default_factory=list)
    # Market-entry reports (M13)
    market_scope: MarketScopeReport | None = None
    forces: list[ForceOut] = field(default_factory=list)
    checks_before_investing: list[str] = field(default_factory=list)
    second_round: SecondRoundOut | None = None  # M14


def _groups(evidence: Evidence, claims: list[CheckedClaim], fields: tuple[tuple[str, str], ...]) -> list[FactGroup]:
    groups: list[FactGroup] = []
    for _, label in fields:
        matching = [evidence.report_claim(c) for c in claims if c.label == label]
        if matching:
            groups.append(FactGroup(label=label, claims=matching))
    return groups


def assemble_report(inputs: ReportInputs) -> Report:
    evidence = Evidence(inputs.claims, inputs.sources, primary_hosts(inputs.findings))
    findings = inputs.findings
    is_market = isinstance(findings, MarketFindings)
    # A market report shows the market's facts where a company report shows the company's.
    if isinstance(findings, MarketFindings):
        company_name, website, prefix, identity_section, fields = (
            findings.market_name,
            None,
            "market.",
            "market.scope_note",
            MARKET_FIELDS,
        )
    else:
        company_name, website, prefix, identity_section, fields = (
            findings.company.name,
            site_root(findings.company.website),
            "company.",
            "company.identity_note",
            COMPANY_FIELDS,
        )

    company_claims = [c for c in inputs.claims if c.section.startswith(prefix)]
    identity = next((c for c in company_claims if c.section == identity_section), None)
    company_overview = CompanyOverview(
        name=company_name,
        website=website,
        identity=evidence.report_claim(identity) if identity else None,
        facts=_groups(evidence, [c for c in company_claims if c is not identity], fields),
    )
    competitors = [
        CompetitorProfile(
            name=comp.name,
            website=site_root(comp.website),
            relation=comp.relation,
            facts=_groups(
                evidence,
                [c for c in inputs.claims if c.section.startswith("competitor.") and c.subject == comp.name],
                COMPETITOR_FIELDS,
            ),
        )
        for comp in competitors_of(findings)
    ]
    narrative = inputs.narrative
    industry = IndustryOverview(
        text=evidence.cite(narrative.industry_overview) if narrative else "",
        claims=[evidence.report_claim(c) for c in inputs.claims if c.section == "industry"],
    )
    analysis = inputs.analysis or AnalysisOut()
    market: MarketSection | None = None
    swot = analysis.swot
    if is_market:  # signals travelled in the SWOT's strengths/weaknesses slots; a market report has no SWOT
        market = MarketSection(
            scope=inputs.market_scope or MarketScopeReport(product=company_name, region="Not stated"),
            forces=inputs.forces,
            signals_for=analysis.swot.strengths,
            signals_against=analysis.swot.weaknesses,
            checks_before_investing=[c.strip() for c in inputs.checks_before_investing if c.strip()],
            not_found=[
                label
                for name, label in MARKET_FIELDS
                if name != "scope_note" and label not in {g.label for g in company_overview.facts}
            ],
        )
        swot = SwotOut()

    missing: list[str] = []
    if inputs.analysis is None:
        missing += ["competitive_comparison", "swot", "market_trends", "opportunities", "risks"]
    if inputs.recommendations is None:
        missing.append("recommendations")
    if narrative is None:
        missing += ["executive_summary", "next_steps"]
    outcome = "succeeded" if not missing and not inputs.step_errors else "partial"

    validation = inputs.validation.model_copy(update={"warnings": [*inputs.validation.warnings, *inputs.warnings]})
    usage = inputs.usage
    meta = ReportMeta(
        query=inputs.query,
        company_name=company_name,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        outcome=outcome,
        missing_sections=[s for s in REPORT_SECTIONS if s in missing],
        step_errors=inputs.step_errors,
        agent_versions=inputs.agent_versions,
        usage=usage,
        total_input_tokens=sum(u.input_tokens for u in usage),
        total_output_tokens=sum(u.output_tokens for u in usage),
        total_tokens=sum(u.total_tokens for u in usage),
        competitors_confirmed=inputs.competitors_confirmed,
        missing_competitors=inputs.missing_competitors,
        mode="market" if is_market else "company",
        second_round=inputs.second_round,
    )
    return Report(
        meta=meta,
        executive_summary=evidence.cite(narrative.executive_summary) if narrative else "",
        company_overview=company_overview,
        industry_overview=industry,
        competitor_landscape=competitors,
        competitive_comparison=analysis.comparison,
        swot=swot,
        market_trends=analysis.trends,
        opportunities=analysis.opportunities,
        risks=analysis.risks,
        recommendations=inputs.recommendations or [],
        next_steps=[s.strip() for s in narrative.actionable_next_steps if s.strip()] if narrative else [],
        references=[
            Reference(ref=i, url=s.url, title=s.title, retrieved_by=str(s.retrieved_by))
            for i, s in enumerate(evidence.cited_sources, start=1)
        ],
        validation=validation,
        key_figures=analysis.key_figures,
        market=market,
    )
