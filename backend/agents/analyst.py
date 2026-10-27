"""Analyst: comparison, SWOT, trends, opportunities and risks — built only from checked claims."""

from __future__ import annotations

import json

from agents.spec import AgentSpec
from schemas.findings import AnalysisFindings
from schemas.report import CheckedClaim
from workflow.claims import current_year, old_source_year

ANALYST = AgentSpec(
    key="analyst",
    version="analyst@5",
    name="Analyst",
    role="Turns checked research claims into a competitive analysis.",
    output_schema=AnalysisFindings,
    timeout_s=120.0,
    instructions=(
        "You are a market analyst. You receive numbered claims (C1, C2 …) about a target company, its"
        " competitors and its industry. Each claim has a fact-check verdict and confidence.",
        "Use ONLY these claims. Every insight must list in evidence_claim_ids the claim ids it is based on.",
        "Prefer supported claims. Never present an 'unsupported' claim as a fact; if you use one, the insight"
        " kind must be 'interpretation' or 'prediction'.",
        "kind: 'fact' ONLY when the insight restates what the cited claims say. Your own conclusions are"
        " 'interpretation'; anything about the future, or with words like could, may, might or likely, is"
        " 'interpretation' or 'prediction'.",
        "MISSING DATA IS NOT A FINDING: if the claims don't cover something (pricing, funding, market share …),"
        " that is a gap in OUR research, not a fact about the company. Never turn it into a strength,"
        " weakness, threat, opportunity or risk (e.g. 'pricing is not transparent'). Put it in data_gaps only.",
        "Be specific to this company: avoid statements that would be true of any company in the industry.",
        "comparison: 4-6 dimensions (e.g. Core offering, Target customers, Pricing, Positioning, Geography)."
        " One cell per company, target company first. Use 'Not publicly available' with no claim ids when"
        " the claims don't cover it. Only include a dimension when at least two companies have data for it.",
        "swot: 2-4 items per quadrant, about the TARGET company.",
        "trends: 2-4 market trends. opportunities: 2-4 gaps or openings for the target company."
        " risks: 2-4 business risks. Opportunities and risks are judgements: their kind is never 'fact'.",
        "Cell values are plain facts. Never write verdict words (Supported, Unsupported …) inside a cell.",
        "data_gaps: important things the claims do not cover (e.g. pricing, funding, market share).",
        "key_figures: up to 8 numbers worth showing in a chart (prices, market size, users, revenue, growth)."
        " Copy each number EXACTLY as written in the claim (6, 10.99, 68.2) with its unit as written"
        " ('USD per user per month', 'USD billion', '%'); never convert, add up or estimate. List in claim_ids"
        " the claims whose text contains that number; use only supported or partially supported claims."
        " Use the same label for figures meant to be compared (e.g. every competitor's 'Entry paid plan price').",
        "Be specific and concise: one sentence per insight.",
        'OLD SOURCES: a claim with "old_source": 2018 rests only on a page from that year. Never present it as'
        " current; say 'in 2018' or leave it out of trends, opportunities and risks.",
    ),
)


def build_analysis_prompt(company: str, competitors: list[str], claims: list[CheckedClaim]) -> str:
    payload = {
        "target_company": company,
        "competitors": competitors,
        "claims": [
            {
                "id": c.id,
                "about": c.subject,
                "topic": c.label,
                "claim": c.text,
                "kind": c.kind,
                "verdict": c.verdict,
                "confidence": c.confidence,
                **({"old_source": year} if (year := old_source_year(c, current_year())) else {}),
            }
            for c in claims
        ],
    }
    return "Analyse the target company against its competitors.\n\n" + json.dumps(payload, ensure_ascii=False)
