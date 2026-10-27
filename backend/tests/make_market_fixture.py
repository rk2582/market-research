# ruff: noqa: E501 — long illustrative sentences
"""Builds frontend/src/modules/research/fixtures/report-market.json through the REAL backend assembler.

Illustrative test data only: fictional players and .example sources (not real research).
Run from backend/ after changing the report shape:
    uv run python -m tests.make_market_fixture
"""

from __future__ import annotations

import json
from pathlib import Path

from schemas.findings import (
    MarketAnalysisFindings,
    MarketFindings,
    MarketStrategy,
    ReportNarrative,
    StrategyRecommendations,
)
from schemas.report import CheckedClaim, MarketScopeReport, SecondRoundOut, StepUsageOut
from schemas.research import SourceCreate
from workflow.claims import extract_claims, gate
from workflow.report_assembler import (
    Evidence,
    ReportInputs,
    assemble_report,
    process_market_analysis,
    process_recommendations,
)

OUT = Path(__file__).resolve().parents[2] / "frontend/src/modules/research/fixtures/report-market.json"

STATS = "https://dairy-stats.example/kerala-2025"
BOARD = "https://dairy-board.example/india-packaged-milk"
NEWS = "https://kerala-news.example/milk-prices-2025"
RULES = "https://food-safety.example/dairy-licence"
TREND = "https://trade-press.example/a2-milk-cities"
COSTS = "https://agri-finance.example/dairy-startup-costs"
FIRM = "https://www.imarcgroup.com/illustrative-kerala-dairy"  # a research-firm page → "estimate"
P = {
    "Periyar Dairy Co-op": "https://periyar-dairy.example",
    "Malabar Farms": "https://malabar-farms.example",
    "GreenCow Organics": "https://greencow.example",
    "Coastline Milk": "https://coastline-milk.example",
}
TITLES = {
    STATS: "Kerala dairy statistics 2025",
    BOARD: "India packaged milk market report 2025",
    NEWS: "Milk prices rise again in Kochi",
    RULES: "Licences for dairy processors",
    TREND: "A2 and organic milk demand in Indian cities",
    COSTS: "What it costs to start a small dairy plant",
    FIRM: "Kerala dairy market report (summary)",
    **{site: f"{name} — home" for name, site in P.items()},
}


def s(text: str, url: str, kind: str = "fact") -> dict:
    return {"text": text, "source_urls": [url], "kind": kind}


def player(name: str, desc: str, offer: str, price: str | None, who: str, pos: str) -> dict:
    site = P[name]
    return {
        "name": name,
        "website": site,
        "relation": "direct",
        "description": s(desc, site),
        "offerings": [s(offer, site)],
        "pricing": s(price, site) if price else None,
        "target_segments": [s(who, site)],
        "positioning": s(pos, site, "interpretation"),
    }


findings = MarketFindings.model_validate(
    {
        "market_name": "Fresh packaged milk in Kerala",
        "scope_note": s(
            "Covers fresh packaged milk sold to households in Kerala; market size is Kerala-level, growth is India-wide.",
            STATS,
        ),
        "market_size": [
            s("Kerala's packaged milk sales were worth ₹6,800 crore in 2024 (Kerala-level).", STATS),
            s("IMARC estimates the Kerala dairy market (all dairy products) at ₹21,000 crore in 2025.", FIRM),
        ],
        "growth": [
            s("India's packaged milk market grew about 7% a year between 2020 and 2024 (India-wide).", BOARD),
            s("The same report forecasts 8% yearly growth to 2030 (India-wide).", BOARD, "prediction"),
        ],
        "customers_demand": [
            s("About 80% of Kerala households buy packaged milk at least once a day.", STATS),
            s("Kerala produces less milk than it consumes and buys the gap from neighbouring states.", STATS),
        ],
        "prices": [s("Toned milk sold for ₹52 per litre in Kochi in March 2025, up from ₹48 in 2023.", NEWS)],
        "supply_chain": [s("Most milk is collected through about 3,000 village co-operative societies.", STATS)],
        "regulation": [s("Every dairy processor needs a state food-safety licence and a pollution clearance.", RULES)],
        "costs_margins": [],  # not found → shown as "Not found in public sources"
        "barriers": [s("The state co-operative controls most village collection points.", STATS)],
        "trends": [
            s("Demand for A2 and organic milk is growing fastest in Kochi and Thiruvananthapuram.", TREND),
            s("Milk subscriptions delivered to the door before 7 am are spreading in cities.", TREND),
        ],
        "players": [
            player(
                "Periyar Dairy Co-op",
                "Periyar Dairy Co-op is the state's largest milk co-operative.",
                "Toned, double-toned and full-cream milk, curd and ghee.",
                "Toned milk at ₹52 per litre.",
                "Households across all districts.",
                "The default, lowest-price choice in most shops.",
            ),
            player(
                "Malabar Farms",
                "Malabar Farms is a private dairy selling in northern Kerala.",
                "Full-cream milk and flavoured milk.",
                "Full-cream milk at ₹62 per litre.",
                "Households and cafes in Kozhikode and Kannur.",
                "Positions itself on freshness and local farms.",
            ),
            player(
                "GreenCow Organics",
                "GreenCow Organics sells certified organic A2 milk by subscription.",
                "Organic A2 milk in glass bottles, delivered daily.",
                "A2 milk at ₹110 per litre on a monthly plan.",
                "Health-conscious families in Kochi.",
                "Premium, subscription-only brand.",
            ),
            player(
                "Coastline Milk",
                "Coastline Milk brings packaged milk from Tamil Nadu into southern Kerala.",
                "Toned milk and curd.",
                None,
                "Shops in Thiruvananthapuram and Kollam.",
                "Competes on wide shop availability.",
            ),
        ],
        "players_shortfall_reason": None,
    }
)

urls = [STATS, BOARD, NEWS, RULES, TREND, FIRM, *P.values()]
sources = [SourceCreate(url=u, title=TITLES[u], excerpt="…", retrieved_by="search") for u in urls]
claims = extract_claims(findings, sources)

PARTIAL = {"Toned milk sold for ₹52"}  # one partly supported claim, one removed, to show the verdict colours
checked: list[CheckedClaim] = []
for c in claims:
    verdict = "partially_supported" if any(c.text.startswith(p) for p in PARTIAL) else "supported"
    if c.text.startswith("Coastline Milk brings"):
        verdict = "unsupported"
    checked.append(
        CheckedClaim(
            **c.model_dump(),
            verdict=verdict,
            confidence="high",
            reason="Checked against the page.",
            checked_by="fact_checker",
            source_year=2019 if c.text.startswith("Milk subscriptions") else None,  # → "Old source (2019)"
        )
    )
kept, validation = gate(checked)
by_text = {c.text: c.id for c in kept}


def cid(prefix: str) -> str:
    return next(i for t, i in by_text.items() if t.startswith(prefix))


evidence = Evidence(kept, sources)


def ins(text: str, *prefixes: str, kind: str = "fact") -> dict:
    return {"text": text, "kind": kind, "evidence_claim_ids": [cid(p) for p in prefixes]}


raw_analysis = MarketAnalysisFindings.model_validate(
    {
        "comparison": [
            {
                "dimension": "Offer",
                "cells": [
                    {"company": n, "value": v, "claim_ids": [cid(v[:12])]}
                    for n, v in [
                        ("Periyar Dairy Co-op", "Toned, double-toned and full-cream milk, curd and ghee."),
                        ("Malabar Farms", "Full-cream milk and flavoured milk."),
                        ("GreenCow Organics", "Organic A2 milk in glass bottles, delivered daily."),
                        ("Coastline Milk", "Toned milk and curd."),
                    ]
                ],
            },
            {
                "dimension": "Price",
                "cells": [
                    {
                        "company": "Periyar Dairy Co-op",
                        "value": "₹52 per litre (toned)",
                        "claim_ids": [cid("Toned milk at")],
                    },
                    {
                        "company": "Malabar Farms",
                        "value": "₹62 per litre (full cream)",
                        "claim_ids": [cid("Full-cream milk at")],
                    },
                    {
                        "company": "GreenCow Organics",
                        "value": "₹110 per litre (A2, monthly)",
                        "claim_ids": [cid("A2 milk at")],
                    },
                    {"company": "Coastline Milk", "value": "Not publicly available", "claim_ids": []},
                ],
            },
        ],
        "forces": [
            {
                "force": "rivalry",
                "rating": "medium",
                "reason": "One large co-operative leads, but private and premium brands are growing.",
                "evidence_claim_ids": [cid("Periyar Dairy Co-op is"), cid("Malabar Farms is")],
            },
            {
                "force": "entry_barriers",
                "rating": "high",
                "reason": "The co-operative controls most village collection points, so new dairies must build their own supply.",
                "evidence_claim_ids": [cid("The state co-operative"), cid("Most milk is collected")],
            },
            {
                "force": "supplier_power",
                "rating": "medium",
                "reason": "Kerala is short of milk and buys from other states, which keeps farm-gate prices firm.",
                "evidence_claim_ids": [cid("Kerala produces less")],
            },
            {
                "force": "buyer_power",
                "rating": "low",
                "reason": "Households buy small amounts daily and prices have risen without demand falling.",
                "evidence_claim_ids": [cid("About 80%"), cid("Toned milk sold")],
            },
        ],
        "signals_for": [
            ins("Kerala consumes more milk than it produces, so demand is already there.", "Kerala produces less"),
            ins("City demand for A2 and organic milk is growing fastest.", "Demand for A2", kind="interpretation"),
            ins(
                "Prices rose from ₹48 to ₹52 a litre in two years without a fall in buying.",
                "Toned milk sold",
                "About 80%",
                kind="interpretation",
            ),
        ],
        "signals_against": [
            ins(
                "The co-operative controls most village collection, so raw milk supply is hard to secure.",
                "The state co-operative",
            ),
            ins(
                "The leading brand is also the cheapest, which squeezes any mass-market newcomer.",
                "Toned milk at",
                kind="interpretation",
            ),
        ],
        "trends": [
            ins("Doorstep subscriptions before 7 am are spreading in cities.", "Milk subscriptions"),
            ins("Packaged milk keeps growing about 7% a year nationally.", "India's packaged milk"),
        ],
        "opportunities": [
            ins(
                "A premium or A2 brand sold by subscription in Kochi.",
                "Demand for A2",
                "Milk subscriptions",
                kind="interpretation",
            ),
            ins("Supplying cafes and hotels, which buy in bulk.", "Households and cafes", kind="interpretation"),
        ],
        "risks": [
            ins("A price war if the co-operative cuts prices.", "Toned milk at", kind="interpretation"),
            ins("Milk shortages in summer raise buying costs.", "Kerala produces less", kind="prediction"),
        ],
        "data_gaps": ["Distributor and shop margins"],
        "key_figures": [
            {
                "label": "Kerala dairy market, all dairy (2025)",
                "company": "Market",
                "value": 21000,
                "unit": "₹ crore",
                "year": 2025,
                "claim_ids": [cid("IMARC estimates")],
            },
            {
                "label": "Price per litre",
                "company": "Periyar Dairy Co-op",
                "value": 52,
                "unit": "₹ per litre",
                "year": None,
                "claim_ids": [cid("Toned milk at")],
            },
            {
                "label": "Price per litre",
                "company": "Malabar Farms",
                "value": 62,
                "unit": "₹ per litre",
                "year": None,
                "claim_ids": [cid("Full-cream milk at")],
            },
            {
                "label": "Price per litre",
                "company": "GreenCow Organics",
                "value": 110,
                "unit": "₹ per litre",
                "year": None,
                "claim_ids": [cid("A2 milk at")],
            },
        ],
    }
)
analysis, forces, warnings = process_market_analysis(raw_analysis, evidence)
fids = {i.text: i.id for i in analysis.all_insights()}


def fid(prefix: str) -> str:
    return next(i for t, i in fids.items() if t.startswith(prefix))


strategy = MarketStrategy.model_validate(
    {
        "recommendations": [
            {
                "priority": 1,
                "title": "Start a premium A2 milk subscription in Kochi",
                "rationale": "City demand for A2 and organic milk is growing fastest, and doorstep subscriptions are spreading. A small premium brand avoids competing head-on with the co-operative on price.",
                "evidence_ids": [fid("City demand"), fid("Doorstep")],
                "impact": "high",
                "next_steps": [
                    "Find 10–20 A2 farms within 50 km of Kochi",
                    "Run a 3-month trial with 200 households",
                    "Price against the ₹110 premium benchmark",
                ],
                "risks_tradeoffs": ["Small niche at first", "Delivery costs before 7 am are high"],
            },
            {
                "priority": 2,
                "title": "Supply cafes and hotels in bulk",
                "rationale": "Private dairies already sell to cafes, and bulk buyers care about steady supply more than the lowest price.",
                "evidence_ids": [fid("Supplying cafes")],
                "impact": "medium",
                "next_steps": ["List 30 cafes and hotels in one city", "Offer a weekly delivery trial"],
                "risks_tradeoffs": ["Longer payment terms", "Bigger buyers push for discounts"],
            },
        ],
        "checks_before_investing": [
            "Ask 3 distributors in Kochi what margin they take on packaged milk.",
            "Visit 5 shops and note the shelf price and brands of every milk on sale.",
            "Confirm the food-safety licence and pollution clearance cost and timeline.",
            "Get quotes for a 5,000-litre-a-day plant from two suppliers.",
            "Ask 20 households in Kochi whether they would pay ₹90–110 a litre for A2 milk.",
        ],
    }
)
recs, rec_warnings = process_recommendations(
    StrategyRecommendations(recommendations=strategy.recommendations), analysis, evidence
)

narrative = ReportNarrative(
    executive_summary=(
        "Kerala buys more packaged milk than it produces, and prices have kept rising, so demand is not the problem"
        f" [{cid('Kerala produces less')}][{cid('Toned milk sold')}]. The hard part is supply: the state co-operative"
        f" controls most village collection points [{cid('The state co-operative')}] and sells the cheapest milk."
        f" The clearest opening is a premium or A2 brand in the cities, where that demand is growing fastest"
        f" [{cid('Demand for A2')}]. Margins and distributor terms are not public — check them before investing."
    ),
    industry_overview=(
        f"Packaged milk keeps growing about 7% a year in India [{cid('India')}], and doorstep subscriptions are"
        f" spreading in Kerala's cities [{cid('Milk subscriptions')}]."
    ),
    actionable_next_steps=[
        "Talk to 3 distributors in Kochi about margins.",
        "Test demand for A2 milk with 20 households.",
        "Get the licence cost and timeline in writing.",
    ],
)

usage = [
    StepUsageOut(
        step="research",
        agent_version="market_researcher@2",
        model="gpt-4.1-mini",
        input_tokens=31000,
        output_tokens=3100,
        total_tokens=34100,
        tool_calls=12,
        duration_ms=48000,
    ),
    StepUsageOut(
        step="validate",
        agent_version="fact_checker@4",
        model="gpt-4.1-mini",
        input_tokens=26000,
        output_tokens=2100,
        total_tokens=28100,
        duration_ms=11000,
    ),
    StepUsageOut(
        step="analyse",
        agent_version="market_analyst@4",
        model="gpt-4.1",
        input_tokens=4200,
        output_tokens=1900,
        total_tokens=6100,
        duration_ms=12000,
    ),
    StepUsageOut(
        step="strategise",
        agent_version="market_strategist@1",
        model="gpt-4.1",
        input_tokens=2100,
        output_tokens=1000,
        total_tokens=3100,
        duration_ms=8000,
    ),
    StepUsageOut(
        step="write",
        agent_version="report_writer@6",
        model="gpt-4.1-mini",
        input_tokens=3800,
        output_tokens=600,
        total_tokens=4400,
        duration_ms=5000,
    ),
]

report = assemble_report(
    ReportInputs(
        query="Milk",
        findings=findings,
        sources=sources,
        claims=kept,
        validation=validation,
        analysis=analysis,
        recommendations=recs,
        narrative=narrative,
        usage=usage,
        warnings=[*warnings, *rec_warnings],
        agent_versions={"researcher": "market_researcher@2"},
        market_scope=MarketScopeReport(product="Fresh packaged milk", region="Kerala", customer_type="households"),
        forces=forces,
        checks_before_investing=strategy.checks_before_investing,
        second_round=SecondRoundOut(
            gaps=[
                "Coastline Milk: read its own website (https://coastline-milk.example); its prices per unit",
                "Costs and margins: start-up costs and typical margins (only if public)",
                'A current source (last 2 years) for: "Milk subscriptions delivered to the door before 7 am are'
                ' spreading in cities." — the only source is from 2019.',
            ],
            filled=1,
            new_claims=2,
            total_tokens=12400,
            duration_ms=38000,
        ),
    )
)
data = report.model_dump(mode="json")
data["meta"]["generated_at"] = "2026-10-27T10:00:00+00:00"
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(OUT.name, "forces", [f.force for f in forces], "warnings", warnings + rec_warnings)
print("claims", validation.claims_total, "supported", validation.supported, "figures", len(report.key_figures))
