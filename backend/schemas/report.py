"""The final market intelligence report (built by code in workflow/report_assembler.py).

Not sent to any LLM, so normal Pydantic rules apply. Every fact carries `refs`: numbers of the
sources in `references` that support it, so the UI can show [1], [2] next to each statement.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from schemas.findings import ClaimKind, Confidence, Verdict

Outcome = Literal["succeeded", "partial", "failed"]

# The 12 sections the product spec asks for, in order.
REPORT_SECTIONS = (
    "executive_summary",
    "company_overview",
    "industry_overview",
    "competitor_landscape",
    "competitive_comparison",
    "swot",
    "market_trends",
    "opportunities",
    "risks",
    "recommendations",
    "next_steps",
    "references",
)


class Claim(BaseModel):
    """One statement from the Researcher, numbered C1, C2 … (internal, between steps)."""

    id: str
    subject: str  # company or competitor name
    section: str  # e.g. "company.funding", "competitor.offerings", "industry"
    label: str  # human label, e.g. "Funding"
    text: str
    kind: ClaimKind
    source_urls: list[str]  # only URLs that were actually retrieved
    cited_but_not_retrieved: list[str] = Field(default_factory=list)
    # Added by code (a competitor's own homepage); kept only if the Fact-Checker says it supports the claim.
    code_added_urls: list[str] = Field(default_factory=list)


class CheckedClaim(Claim):
    verdict: Verdict
    confidence: Confidence
    reason: str
    checked_by: Literal["code", "fact_checker"]
    source_year: int | None = None  # M14: year stated on the supporting page (or in its URL)


class ReportClaim(BaseModel):
    id: str
    text: str
    kind: ClaimKind
    verdict: Verdict
    confidence: Confidence
    refs: list[int]
    # M13: rests on a market-research firm's summary page (one firm's estimate, not an official figure).
    estimate: bool = False
    # M14: a trend, price or recent-news claim whose only dated source is more than 3 years old.
    old_source_year: int | None = None


class FactGroup(BaseModel):
    label: str
    claims: list[ReportClaim]


class CompanyOverview(BaseModel):
    name: str
    website: str | None
    identity: ReportClaim | None
    facts: list[FactGroup]


class CompetitorProfile(BaseModel):
    name: str
    website: str | None
    relation: Literal["direct", "indirect"]
    facts: list[FactGroup]


class IndustryOverview(BaseModel):
    text: str
    claims: list[ReportClaim]


class ComparisonCellOut(BaseModel):
    company: str
    value: str
    refs: list[int]


class ComparisonRowOut(BaseModel):
    dimension: str
    cells: list[ComparisonCellOut]


class InsightOut(BaseModel):
    id: str  # F1, F2 …
    text: str
    kind: ClaimKind
    claim_ids: list[str]
    refs: list[int]


class SwotOut(BaseModel):
    strengths: list[InsightOut] = Field(default_factory=list)
    weaknesses: list[InsightOut] = Field(default_factory=list)
    opportunities: list[InsightOut] = Field(default_factory=list)
    threats: list[InsightOut] = Field(default_factory=list)


class RecommendationOut(BaseModel):
    priority: int
    title: str
    rationale: str
    impact: Literal["high", "medium", "low"]
    next_steps: list[str]
    risks_tradeoffs: list[str]
    evidence_ids: list[str]
    refs: list[int]
    warning: str | None = None


class Reference(BaseModel):
    ref: int
    url: str
    title: str | None
    retrieved_by: str


class ValidationSummary(BaseModel):
    claims_total: int = 0
    supported: int = 0
    partially_supported: int = 0
    unsupported: int = 0
    contradicted: int = 0  # removed from the report
    warnings: list[str] = Field(default_factory=list)


class StepUsageOut(BaseModel):
    step: str
    agent_version: str | None
    model: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tool_calls: int = 0
    duration_ms: int | None = None


class SecondRoundOut(BaseModel):
    """M14: one targeted research round after fact-checking, for the gaps code found."""

    gaps: list[str] = Field(default_factory=list)  # what was asked for, in plain words
    filled: int = 0  # gaps no longer found afterwards
    new_claims: int = 0  # new claims kept after fact-checking
    total_tokens: int = 0
    duration_ms: int | None = None
    error: str | None = None  # the round failed; the report uses the first round's evidence


class ReportMeta(BaseModel):
    query: str
    company_name: str
    generated_at: str
    outcome: Outcome
    missing_sections: list[str] = Field(default_factory=list)
    step_errors: dict[str, str] = Field(default_factory=dict)
    agent_versions: dict[str, str] = Field(default_factory=dict)
    usage: list[StepUsageOut] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    mode: Literal["company", "market"] = "company"  # M13: market-entry reports
    # M12: the user confirmed the competitor list; confirmed ones the Researcher could not profile.
    competitors_confirmed: bool = False
    missing_competitors: list[str] = Field(default_factory=list)
    second_round: SecondRoundOut | None = None  # M14: the research-more round, when it ran


class KeyFigureOut(BaseModel):
    """A number for charts, kept only when the number appears in a verified claim it cites (checked in code)."""

    label: str
    company: str
    value: float
    unit: str
    year: int | None = None
    claim_ids: list[str] = Field(default_factory=list)
    refs: list[int] = Field(default_factory=list)
    estimate: bool = False  # M13: only backed by research-firm estimates


class ForceOut(BaseModel):
    force: str  # rivalry | entry_barriers | supplier_power | buyer_power | substitutes
    rating: str  # low | medium | high
    reason: str
    claim_ids: list[str]
    refs: list[int]


class MarketScopeReport(BaseModel):
    product: str
    region: str
    customer_type: str | None = None


class MarketSection(BaseModel):
    """Market-entry reports only (M13). Players are in competitor_landscape; market facts in company_overview."""

    scope: MarketScopeReport
    forces: list[ForceOut] = Field(default_factory=list)
    signals_for: list[InsightOut] = Field(default_factory=list)
    signals_against: list[InsightOut] = Field(default_factory=list)
    checks_before_investing: list[str] = Field(default_factory=list)
    # Market-snapshot topics with no claim at all — shown as "Not found in public sources", never guessed.
    not_found: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Evidence to help you decide — not a recommendation to invest and not financial advice. "
        "Do the checks in 'Check before you invest' first."
    )


class Report(BaseModel):
    meta: ReportMeta
    executive_summary: str
    company_overview: CompanyOverview
    industry_overview: IndustryOverview
    competitor_landscape: list[CompetitorProfile]
    competitive_comparison: list[ComparisonRowOut]
    swot: SwotOut
    market_trends: list[InsightOut]
    opportunities: list[InsightOut]
    risks: list[InsightOut]
    recommendations: list[RecommendationOut]
    next_steps: list[str]
    references: list[Reference]
    validation: ValidationSummary
    key_figures: list[KeyFigureOut] = Field(default_factory=list)  # added in M11; older reports have none
    market: MarketSection | None = None  # M13: market-entry reports only


class AnalysisOut(BaseModel):
    """The Analyst's output after code checks: insights numbered F1 …, evidence verified."""

    comparison: list[ComparisonRowOut] = Field(default_factory=list)
    swot: SwotOut = Field(default_factory=SwotOut)
    trends: list[InsightOut] = Field(default_factory=list)
    opportunities: list[InsightOut] = Field(default_factory=list)
    risks: list[InsightOut] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    key_figures: list[KeyFigureOut] = Field(default_factory=list)

    def all_insights(self) -> list[InsightOut]:
        s = self.swot
        return [
            *s.strengths,
            *s.weaknesses,
            *s.opportunities,
            *s.threats,
            *self.trends,
            *self.opportunities,
            *self.risks,
        ]
