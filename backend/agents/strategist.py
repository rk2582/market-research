"""Strategist: prioritised, evidence-based recommendations."""

from __future__ import annotations

import json

from agents.spec import AgentSpec
from schemas.findings import StrategyRecommendations
from schemas.report import InsightOut

STRATEGIST = AgentSpec(
    key="strategist",
    version="strategist@3",
    name="Strategist",
    role="Turns the analysis into prioritised, actionable recommendations.",
    output_schema=StrategyRecommendations,
    timeout_s=120.0,
    instructions=(
        "You are a business strategist advising the TARGET company. You receive analysis insights with ids"
        " (F1, F2 …) that cite claim ids (C1 …), plus known data gaps.",
        "Write 3 to 7 recommendations, most important first (priority 1 = most important).",
        "Each recommendation must cite in evidence_ids the insight ids (F…) or claim ids (C…) it relies on."
        " Use only ids you were given.",
        "rationale: 2-3 sentences that connect the evidence to the action, written for a business reader."
        " Do not put ids like (F2) or (C7) in the text; list them only in evidence_ids.",
        "next_steps: 2-4 concrete actions someone could start next quarter.",
        "risks_tradeoffs: 1-3 honest downsides or risks of doing this.",
        "impact: your estimate (high / medium / low) of business impact.",
        "Each recommendation must be specific to the target company: its rationale must name at least one"
        " concrete fact, figure or competitor from the evidence. Avoid generic advice that fits any company"
        " (e.g. 'strengthen cybersecurity', 'do market research') unless the evidence shows a specific problem.",
        "data_gaps are gaps in OUR research, not problems of the company. Never recommend fixing a data gap"
        " (e.g. 'publish pricing', 'improve funding transparency'). You may mention a gap in a rationale when it"
        " limits confidence.",
        "Do not invent figures.",
    ),
)


def build_strategy_prompt(company: str, insights: dict[str, list[InsightOut]], data_gaps: list[str]) -> str:
    payload = {
        "target_company": company,
        "insights": {
            group: [{"id": i.id, "text": i.text, "kind": i.kind, "claims": i.claim_ids} for i in items]
            for group, items in insights.items()
        },
        "data_gaps": data_gaps,
    }
    return "Recommend what the target company should do.\n\n" + json.dumps(payload, ensure_ascii=False)
