"""Structured outputs the agents must return (sent to OpenAI as a strict JSON schema).

OpenAI "strict" structured outputs support only part of JSON Schema, so these models stay simple:
- every field is required (use `X | None` for "may be unknown"), no default values;
- URLs are plain strings, list sizes aren't constrained here;
- fields whose type is another model (or model | None) have NO description: OpenAI rejects
  "$ref" combined with other keywords. Their guidance lives in the agent's instructions instead.
Extra rules (valid URLs, 3–5 competitors, sources actually retrieved) are checked in our own code.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ClaimKind = Literal["fact", "interpretation", "prediction"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourcedText(_Strict):
    text: str = Field(description="One clear statement.")
    source_urls: list[str] = Field(
        description="URLs of pages you actually searched or read in this task that support the statement."
    )
    kind: ClaimKind = Field(
        description="fact = stated by a source; interpretation = your reading; prediction = about the future."
    )


class CompanyProfile(_Strict):
    name: str
    website: str | None
    identity_note: SourcedText  # which organisation was matched and why (see instructions)
    description: SourcedText
    industry: SourcedText
    products_services: list[SourcedText]
    customer_segments: list[SourcedText]
    geographic_presence: list[SourcedText]
    business_model: SourcedText | None  # null if not publicly available
    pricing: SourcedText | None
    funding: SourcedText | None
    recent_developments: list[SourcedText] = Field(description="Last 12 months; include the date in the text.")
    positioning_usp: SourcedText | None


class Competitor(_Strict):
    name: str
    website: str | None
    relation: Literal["direct", "indirect"]
    description: SourcedText
    offerings: list[SourcedText]
    pricing: SourcedText | None
    target_segments: list[SourcedText]
    positioning: SourcedText | None


# ---------------------------------------------------------------------------
# Identifier (M12): what the user typed, before the full research
# ---------------------------------------------------------------------------


class CompanyMatch(_Strict):
    name: str = Field(description="The company's usual name.")
    website: str | None = Field(description="Its homepage, e.g. https://monzo.com, or null if unknown.")
    description: str = Field(description="One short sentence: what the company does and where.")
    source_url: str = Field(description="A URL returned by your tools in this task that shows this company.")


class ProductLine(_Strict):
    name: str = Field(description="A main product line in the company's main market, e.g. 'Instant noodles'.")
    brands: list[str] = Field(description="The company's flagship brands in it, e.g. ['Maggi']. May be empty.")


class SuggestedCompetitor(_Strict):
    name: str
    website: str | None = Field(description="Its homepage, or null if unknown.")
    competes_in: str = Field(description="Which of the company's product lines it competes in, e.g. 'Instant noodles'.")
    reason: str = Field(description="Its rival brand or offer in that line, e.g. 'Yippee noodles', in a few words.")
    source_url: str = Field(description="A URL returned by your tools in this task that supports this.")


class MarketScope(_Strict):
    product: str = Field(description="The product or business idea, as specific as the input allows.")
    region: str | None = Field(description="Country, state or city if the input names one, else null.")
    customer_type: str | None = Field(description="Who buys it (households, cafés, businesses …) if stated, else null.")


class Identification(_Strict):
    kind: Literal["company", "market"] = Field(
        description="company = a specific organisation, brand or website; "
        "market = a product, category, industry or business idea."
    )
    matches: list[CompanyMatch] = Field(
        description="Companies the input could mean, most likely first (1-3). "
        "For a market: companies whose name is that word, if any."
    )
    product_lines: list[ProductLine] = Field(
        description="For a company: its 1-4 biggest product lines (with brands), biggest first. For a market: empty."
    )
    competitors: list[SuggestedCompetitor] = Field(
        description="For a company: 3-6 leading rivals of the FIRST match in those product lines. For a market: empty."
    )
    market: MarketScope | None
    note: str = Field(description="One short sentence for the user, e.g. why several matches are shown.")


class ResearchFindings(_Strict):
    company: CompanyProfile
    competitors: list[Competitor] = Field(description="3 to 5 relevant competitors, most relevant first.")
    competitor_shortfall_reason: str | None = Field(description="Required only if fewer than 3 competitors.")
    industry_context: list[SourcedText] = Field(description="Market size, trends or dynamics relevant to the company.")


class MarketFindings(_Strict):
    """Market-entry research (M13): one product in one region, and the main players selling it there."""

    market_name: str = Field(description="Short name of the market, e.g. 'Fresh packaged milk in Kerala'.")
    scope_note: SourcedText  # what exactly is covered: product, region, customers, and at what level data exists
    market_size: list[SourcedText] = Field(description="Size of the market (value or volume) with year and region.")
    growth: list[SourcedText] = Field(description="Growth rates or forecasts, with years and who forecasts them.")
    customers_demand: list[SourcedText] = Field(description="Who buys, how much, how often, what drives demand.")
    prices: list[SourcedText] = Field(description="Typical retail or wholesale prices, with units and dates.")
    supply_chain: list[SourcedText] = Field(description="Sourcing, production, distribution and channels.")
    regulation: list[SourcedText] = Field(description="Licences, standards and rules that apply in that region.")
    costs_margins: list[SourcedText] = Field(description="Start-up costs and typical margins, only if public.")
    barriers: list[SourcedText] = Field(description="What makes entry hard: capital, brands, distribution, rules.")
    trends: list[SourcedText] = Field(description="Market trends and dynamics in that region.")
    players: list[Competitor] = Field(description="3 to 6 main players selling this product in this region.")
    players_shortfall_reason: str | None = Field(description="Required only if fewer than 3 players.")


# ---------------------------------------------------------------------------
# Fact-Checker
# ---------------------------------------------------------------------------

Verdict = Literal["supported", "partially_supported", "unsupported", "contradicted"]
Confidence = Literal["high", "medium", "low"]


class ClaimVerdict(_Strict):
    claim_id: str
    verdict: Verdict
    confidence: Confidence
    reason: str = Field(description="One short sentence: what the excerpts say (or don't say) about the claim.")
    supporting_urls: list[str] = Field(
        description="The claim's source URLs whose excerpts contain the evidence. Empty if none do."
    )
    source_year: int | None = Field(
        description="The year the supporting page was published or last updated, as stated in its excerpt "
        "(e.g. a dateline or 'Updated 12 March 2024'). Null if the excerpt states no such date."
    )


class ValidationResult(_Strict):
    verdicts: list[ClaimVerdict] = Field(description="Exactly one verdict for every claim id you were given.")


# ---------------------------------------------------------------------------
# Analyst
# ---------------------------------------------------------------------------


class Insight(_Strict):
    text: str = Field(description="One clear sentence.")
    kind: ClaimKind
    evidence_claim_ids: list[str] = Field(description="Claim ids (e.g. C3) this insight is based on. At least one.")


class ComparisonCell(_Strict):
    company: str
    value: str = Field(description="Short value, or 'Not publicly available'.")
    claim_ids: list[str]


class ComparisonRow(_Strict):
    dimension: str = Field(description="e.g. Core offering, Target customers, Pricing, Positioning, Geography.")
    cells: list[ComparisonCell] = Field(description="One cell per company: the target company first.")


class Swot(_Strict):
    strengths: list[Insight]
    weaknesses: list[Insight]
    opportunities: list[Insight]
    threats: list[Insight]


class KeyFigure(_Strict):
    label: str = Field(
        description="What is measured, worded the same for figures meant to be compared, e.g. 'Entry paid plan price'."
    )
    company: str = Field(description="The company it is about, or 'Market' for market-wide figures.")
    value: float = Field(
        description="The number exactly as written in the cited claim (6, 10.99, 68.2), not converted."
    )
    unit: str = Field(
        description="Unit as in the claim, e.g. 'USD per user per month', 'USD billion', '%', 'customers'."
    )
    year: int | None = Field(description="The year the figure applies to, only if the claim states it.")
    claim_ids: list[str] = Field(description="Claim ids whose text contains this exact number.")


class AnalysisFindings(_Strict):
    comparison: list[ComparisonRow]
    swot: Swot
    trends: list[Insight]
    opportunities: list[Insight] = Field(description="Market gaps and openings for the target company.")
    risks: list[Insight]
    data_gaps: list[str] = Field(description="Important things that could not be found in the evidence.")
    key_figures: list[KeyFigure] = Field(description="Up to 8 numbers worth charting, each copied from a claim.")


ForceName = Literal["rivalry", "entry_barriers", "supplier_power", "buyer_power", "substitutes"]


class ForceRating(_Strict):
    force: ForceName
    rating: Literal["low", "medium", "high"] = Field(
        description="How strong this force is (high rivalry / high barriers = harder for a newcomer)."
    )
    reason: str = Field(description="One sentence based on the claims.")
    evidence_claim_ids: list[str] = Field(description="Claim ids this rating is based on. At least one.")


class MarketAnalysisFindings(_Strict):
    comparison: list[ComparisonRow] = Field(description="The main players compared; one cell per player.")
    forces: list[ForceRating] = Field(description="The five forces, each rated once, only where the claims allow.")
    signals_for: list[Insight] = Field(description="Evidence that argues FOR entering this market.")
    signals_against: list[Insight] = Field(description="Evidence that argues AGAINST entering this market.")
    trends: list[Insight]
    opportunities: list[Insight] = Field(description="Gaps or openings a newcomer could use.")
    risks: list[Insight]
    data_gaps: list[str] = Field(description="Important things that could not be found in the evidence.")
    key_figures: list[KeyFigure] = Field(description="Up to 8 numbers worth charting, each copied from a claim.")


# ---------------------------------------------------------------------------
# Strategist
# ---------------------------------------------------------------------------


class RecommendationDraft(_Strict):
    priority: int = Field(description="1 = most important.")
    title: str
    rationale: str = Field(description="Why, in 2-3 sentences, referring to the evidence.")
    evidence_ids: list[str] = Field(description="Insight ids (F3) or claim ids (C7) that support this.")
    impact: Literal["high", "medium", "low"]
    next_steps: list[str] = Field(description="2-4 concrete actions.")
    risks_tradeoffs: list[str]


class StrategyRecommendations(_Strict):
    recommendations: list[RecommendationDraft] = Field(description="3 to 7 recommendations.")


class MarketStrategy(_Strict):
    recommendations: list[RecommendationDraft] = Field(description="3 to 5 ways to enter this market (entry options).")
    checks_before_investing: list[str] = Field(
        description="4-8 concrete real-world checks to do before investing, e.g. 'Ask 3 distributors their margin'."
    )


# ---------------------------------------------------------------------------
# Report Writer
# ---------------------------------------------------------------------------


class ReportNarrative(_Strict):
    executive_summary: str = Field(description="150-250 words. Cite claims inline like [C4].")
    industry_overview: str = Field(description="100-200 words. Cite claims inline like [C30].")
    actionable_next_steps: list[str] = Field(description="3-6 short, concrete next steps.")


# ---------------------------------------------------------------------------
# Second research round (M14): only the gaps code found, nothing else
# ---------------------------------------------------------------------------

GapField = Literal[
    # company (company reports)
    "pricing",
    "funding",
    "recent_developments",
    "products_services",
    # a competitor / player
    "description",
    "offerings",
    "target_segments",
    "positioning",
    # the market (market reports)
    "market_size",
    "growth",
    "customers_demand",
    "prices",
    "supply_chain",
    "regulation",
    "costs_margins",
    "barriers",
    "trends",
    # industry context (company reports)
    "industry_context",
]


class GapStatement(_Strict):
    gap: int = Field(description="The number of the gap in the brief that this statement fills.")
    about: str = Field(description="Exactly the name given for that gap (the company, player or market).")
    field: GapField = Field(description="Where the statement belongs, as given for that gap.")
    statement: SourcedText
    website: str | None = Field(description="The player's own homepage if the gap asks for it, else null.")


class GapFindings(_Strict):
    statements: list[GapStatement] = Field(description="New statements for the gaps only, each with its sources.")
    not_found: list[int] = Field(description="Numbers of the gaps you could not fill from public sources.")
