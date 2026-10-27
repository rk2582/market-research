"""Report Writer: the prose parts only. Tables, SWOT and references are assembled by code."""

from __future__ import annotations

import json
from typing import Any

from agents.spec import AgentSpec
from schemas.findings import ReportNarrative

REPORT_WRITER = AgentSpec(
    key="report_writer",
    version="report_writer@6",
    name="Report Writer",
    role="Writes the executive summary, industry overview and next steps of the report.",
    output_schema=ReportNarrative,
    timeout_s=120.0,
    instructions=(
        "You write the prose parts of a market intelligence report for business readers.",
        "Use ONLY the material you are given. Do not add facts, numbers or names that are not in it.",
        "Cite claims inline with their ids in square brackets, e.g. 'Notion raised $275M in 2021 [C12].'"
        " Only cite claim ids that appear in the material. Write each id separately, e.g. [C4, C5, C6];"
        " never ranges like C4-C6, never insight ids (F…), and no other text in square brackets.",
        "executive_summary: 150-250 words — who the company is, its position against competitors, the key"
        " opportunities and risks, and the top recommendations.",
        "industry_overview: 100-200 words, based on the industry claims and trends.",
        "actionable_next_steps: 3-6 short, concrete steps, drawn from the recommendations.",
        "MARKET-ENTRY material (mode 'market'): executive_summary is the bottom line for someone deciding whether to"
        " enter the market — what the market is, its size and growth, the main players, the strongest signals for"
        " and against, and the most promising entry options. Be balanced. Never tell the reader to invest or not."
        " industry_overview covers the market's trends. actionable_next_steps come from the checks before investing.",
        'ESTIMATES: a claim marked "estimate": true rests on a market-research firm\'s summary page (other pages'
        " often copy it). Never open the summary with it and never state it as plain fact: write e.g."
        " 'one research firm estimates …'."
        " Say exactly what a figure measures as the claim says it (e.g. 'the dairy market', not 'the milk market').",
        "If not_found_in_public_sources lists topics, say briefly that they were not found in public sources.",
        'OLD SOURCES: a claim with "old_source": 2018 rests only on a page from that year. Never present it as'
        " current; say 'in 2018' if you use it.",
        "Plain, clear English. No marketing language. No headings or markdown inside the text.",
    ),
)


def build_writer_prompt(material: dict[str, Any]) -> str:
    return "Write the report text from this material.\n\n" + json.dumps(material, ensure_ascii=False)
