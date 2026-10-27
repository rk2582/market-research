"""M13: market-entry mode — market findings → claims, five-forces and signals checks, the market report,
and a whole market run through the API (fake OpenAI and Tavily)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from db.models.research import CompanyRow, ResearchRunRow
from schemas.findings import ClaimVerdict, KeyFigure, MarketAnalysisFindings, MarketFindings
from schemas.research import SourceCreate
from tests.fakes import FakeOpenAI, FakeTavily, narrative_for, prompt_payload, tool_call
from tests.test_research_api import API, api, wait_until_finished
from workflow.claims import (
    dedupe_findings,
    drop_thin_players,
    extract_claims,
    is_estimate,
    is_research_firm,
    merge_verdicts,
)
from workflow.report_assembler import Evidence, process_key_figures, process_market_analysis

STATS = "https://keralastats.example/dairy-2025"
MILMA = "https://www.milma.com"
NEWS = "https://news.example/kerala-milk-prices"
FIRM = "https://www.imarcgroup.com/kerala-dairy-market"  # a market-research firm → estimate


def s(text: str, url: str = STATS, kind: str = "fact") -> dict[str, Any]:
    return {"text": text, "source_urls": [url], "kind": kind}


def player(name: str, site: str) -> dict[str, Any]:
    return {
        "name": name,
        "website": site + "/about",
        "relation": "direct",
        "description": s(f"{name} sells packaged milk in Kerala.", site),
        "offerings": [s("Toned and full-cream milk.", site)],
        "pricing": None,
        "target_segments": [s("Households in Kerala.", site)],
        "positioning": None,
    }


def thin_player(name: str) -> dict[str, Any]:
    """One vague sourced line, nothing else: not enough to profile."""
    return {
        "name": name,
        "website": None,
        "relation": "direct",
        "description": s(f"{name} is a known player in Kerala.", STATS),
        "offerings": [{"text": "Dairy products.", "source_urls": [], "kind": "fact"}],
        "pricing": None,
        "target_segments": [],
        "positioning": None,
    }


def market_findings(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "market_name": "Fresh packaged milk in Kerala",
        "scope_note": s("Covers packaged fresh milk sold to households in Kerala; some figures are India-wide."),
        "market_size": [
            s("Kerala's dairy market was worth ₹12,400 crore in 2024 (Kerala-level)."),
            s("IMARC estimates the Kerala dairy market at ₹70,610 crore in 2025.", FIRM),
        ],
        "growth": [s("Demand for packaged milk grew 6% a year from 2020 to 2024.", kind="fact")],
        "customers_demand": [s("Most households buy milk daily from local shops.", NEWS)],
        "prices": [s("Toned milk sells for ₹50 per litre in Kochi (2025).", NEWS)],
        "supply_chain": [s("Most milk is collected through village co-operatives.")],
        "regulation": [s("Dairy processors need an FSSAI licence.", NEWS)],
        "costs_margins": [],
        "barriers": [s("Milma controls most co-operative collection in Kerala.", MILMA)],
        "trends": [s("Demand for A2 and organic milk is rising in cities.", NEWS)],
        "players": [
            player("Milma", MILMA),
            player("Amul", "https://amul.com"),
            player("Milma", MILMA),
            thin_player("Jeeva"),
        ],
        "players_shortfall_reason": None,
    }
    data.update(overrides)
    return data


def milk_tavily() -> FakeTavily:
    return FakeTavily(
        search_results={
            "Kerala packaged milk market": [
                {"url": STATS, "title": "Kerala dairy statistics 2025", "content": "₹12,400 crore in 2024"},
                {"url": NEWS, "title": "Milk prices in Kerala", "content": "₹50 per litre"},
                {"url": MILMA + "/", "title": "Milma", "content": "Kerala Co-operative Milk Marketing Federation"},
                {"url": FIRM, "title": "Kerala dairy market report", "content": "₹70,610 crore in 2025"},
            ]
        },
        pages={"https://amul.com": "Amul packaged milk across India."},
    )


def market_analysis(claim_ids: list[str]) -> dict[str, Any]:
    first, last = claim_ids[0], claim_ids[-1]

    def insight(text: str, ids: list[str], kind: str = "fact") -> dict[str, Any]:
        return {"text": text, "kind": kind, "evidence_claim_ids": ids}

    return {
        "comparison": [
            {
                "dimension": "Offer",
                "cells": [
                    {"company": "Milma", "value": "Toned and full-cream milk", "claim_ids": [first]},
                    {"company": "Amul", "value": "Packaged milk", "claim_ids": [last]},
                ],
            }
        ],
        "forces": [
            {
                "force": "rivalry",
                "rating": "high",
                "reason": "Milma dominates collection.",
                "evidence_claim_ids": [first],
            },
            {"force": "rivalry", "rating": "low", "reason": "Second rating.", "evidence_claim_ids": [first]},
            {
                "force": "buyer_power",
                "rating": "medium",
                "reason": "Daily small purchases.",
                "evidence_claim_ids": ["C999"],
            },
            {
                "force": "substitutes",
                "rating": "low",
                "reason": "No public data on substitutes.",
                "evidence_claim_ids": [first],
            },
            {
                "force": "entry_barriers",
                "rating": "high",
                "reason": "Co-operatives control supply.",
                "evidence_claim_ids": [last],
            },
        ],
        "signals_for": [insight("Demand grew 6% a year.", [first])],
        "signals_against": [insight("Milma controls collection.", [last]), insight("Invented.", ["C999"])],
        "trends": [insight("A2 milk demand rising.", [last])],
        "opportunities": [insight("Premium A2 niche in cities.", [last], "fact")],
        "risks": [insight("Price war with Milma.", [first])],
        "data_gaps": ["Margins"],
        "key_figures": [],
    }


def market_strategy(insight_ids: list[str]) -> dict[str, Any]:
    return {
        "recommendations": [
            {
                "priority": 1,
                "title": "Start with a premium A2 milk brand in Kochi",
                "rationale": "City demand for A2 milk is rising.",
                "evidence_ids": [insight_ids[0]],
                "impact": "medium",
                "next_steps": ["Find A2 farms", "Test in 5 shops"],
                "risks_tradeoffs": ["Small niche"],
            }
        ],
        "checks_before_investing": ["Ask 3 distributors in Kochi their margin", " ", "Confirm the FSSAI licence cost"],
    }


# --- claims and analysis (no LLM) -----------------------------------------------------------------


def test_market_findings_become_numbered_claims():
    findings = dedupe_findings(MarketFindings.model_validate(market_findings()))
    assert [p.name for p in findings.players] == ["Milma", "Amul", "Jeeva"]  # repeated player removed
    findings = findings.model_copy(update={"players": findings.players[:2]})  # Jeeva: see the thin-player test
    sources = [SourceCreate(url=u, retrieved_by="search") for u in (STATS, NEWS, MILMA)]
    claims = extract_claims(findings, sources)
    by_section = {c.section: c for c in claims}
    assert claims[0].section == "market.scope_note" and claims[0].label == "Scope"
    assert claims[0].subject == "Fresh packaged milk in Kerala"
    assert (
        by_section["market.prices"].label == "Prices" and by_section["market.regulation"].label == "Licences and rules"
    )
    assert "market.costs_margins" not in by_section  # nothing public: nothing invented
    assert by_section["industry"].label == "Market trends"
    assert {c.subject for c in claims if c.section.startswith("competitor.")} == {"Milma", "Amul"}
    assert next(c for c in claims if c.subject == "Amul").source_urls == []  # amul.com was not retrieved


def test_research_firm_pages_are_estimates_in_claims_and_key_figures():
    assert is_research_firm(FIRM) and is_research_firm("https://reports.mordorintelligence.com/x")
    assert not is_research_firm(STATS) and not is_research_firm("https://imarcgroup.com.evil.example/")
    sources = [SourceCreate(url=u, retrieved_by="search") for u in (STATS, FIRM, MILMA)]
    claims = extract_claims(MarketFindings.model_validate(market_findings()), sources)
    checked = merge_verdicts(
        claims,
        [
            ClaimVerdict(
                claim_id=c.id, verdict="supported", confidence="high", reason="ok", supporting_urls=[], source_year=None
            )
            for c in claims
        ],
        sources,
    )
    firm = next(c for c in checked if c.source_urls == [FIRM])
    official = next(c for c in checked if c.text.startswith("Kerala's dairy market"))
    assert is_estimate(firm) and not is_estimate(official)
    mixed = firm.model_copy(update={"source_urls": [FIRM, STATS]})
    assert is_estimate(mixed)  # a blog or second page next to the firm's often just copies its number
    assert not is_estimate(firm.model_copy(update={"source_urls": []}))
    evidence = Evidence(checked, sources)
    assert evidence.report_claim(firm).estimate and not evidence.report_claim(official).estimate
    figures, _ = process_key_figures(
        [
            KeyFigure(
                label="Dairy market", company="Market", value=70610, unit="₹ crore", year=2025, claim_ids=[firm.id]
            ),
            KeyFigure(
                label="Dairy market", company="Market", value=12400, unit="₹ crore", year=2024, claim_ids=[official.id]
            ),
        ],
        evidence,
    )
    assert [(f.value, f.estimate) for f in figures] == [(70610, True), (12400, False)]


def test_force_ratings_need_sourced_evidence_and_signals_follow_the_insight_rules():
    sources = [SourceCreate(url=u, retrieved_by="search") for u in (STATS, NEWS, MILMA)]
    claims = extract_claims(MarketFindings.model_validate(market_findings()), sources)
    verdicts = [
        ClaimVerdict(
            claim_id=c.id, verdict="supported", confidence="high", reason="ok", supporting_urls=[], source_year=None
        )
        for c in claims
    ]
    checked = merge_verdicts(claims, verdicts, sources)
    ids = [c.id for c in checked if c.source_urls]
    raw = MarketAnalysisFindings.model_validate(market_analysis(ids))
    analysis, forces, warnings = process_market_analysis(raw, Evidence(checked, sources))
    assert [(f.force, f.rating) for f in forces] == [("rivalry", "high"), ("entry_barriers", "high")]  # in order
    assert all(f.refs for f in forces)
    assert "Dropped a second rating for rivalry." in warnings
    assert "Dropped the buyer power rating: no sourced evidence behind it." in warnings
    assert "Dropped the substitutes rating: no sourced evidence behind it." in warnings  # "no public data" = a gap
    assert [i.text for i in analysis.swot.strengths] == ["Demand grew 6% a year."]  # signals for
    assert [i.text for i in analysis.swot.weaknesses] == ["Milma controls collection."]  # signals against
    assert any(w.startswith("Dropped signal against insight with no valid evidence") for w in warnings)
    assert analysis.opportunities[0].kind == "interpretation"  # M10 rule still applies


# --- a whole market run through the API -------------------------------------------------------------


def market_script() -> dict[str, list[Any]]:
    def analyst(body: dict[str, Any]) -> dict[str, Any]:
        ids = [c["id"] for c in prompt_payload(body)["claims"]]
        return market_analysis(ids)

    return {
        "MarketFindings": [[tool_call("search_web", query="Kerala packaged milk market")], market_findings()],
        "ValidationResult": [
            lambda body: {
                "verdicts": [
                    {
                        "claim_id": c["id"],
                        "verdict": "supported",
                        "confidence": "high",
                        "reason": "ok",
                        "supporting_urls": [],
                        "source_year": None,
                    }
                    for c in prompt_payload(body)["claims"]
                ]
            }
        ],
        "MarketAnalysisFindings": [analyst],
        "MarketStrategy": [market_strategy(["F1", "F2"])],
        "ReportNarrative": [narrative_for("C2")],
    }


MILK = {
    "query": "Milk",
    "mode": "market",
    "market": {"product": " fresh packaged milk ", "region": "kerala", "customer_type": "households"},
}


async def test_a_market_run_produces_a_market_entry_report(tmp_path: Path):
    openai = FakeOpenAI(market_script())
    async with api(tmp_path, openai=openai, tavily=milk_tavily()) as (client, app):
        started = await client.post(API, json=MILK)
        assert started.status_code == 202
        summary = started.json()
        assert summary["mode"] == "market" and summary["company_name"] == "Fresh packaged milk · Kerala"
        detail = await wait_until_finished(client, summary["id"])
        report = (await client.get(f"{API}/{summary['id']}/report")).json()
        listed = (await client.get(API)).json()["items"][0]
        async with app.state.database.session() as session:
            run = await session.get(ResearchRunRow, uuid.UUID(summary["id"]))
            companies = await session.scalar(select(func.count()).select_from(CompanyRow))

    assert detail["status"] == "succeeded", detail
    prompt = str(openai.requests_for("MarketFindings")[0]["messages"])
    assert "Research the market for: Fresh packaged milk. Region: Kerala. Customers: households." in prompt
    meta = report["meta"]
    assert meta["mode"] == "market" and meta["company_name"] == "Fresh packaged milk in Kerala"
    assert set(meta["agent_versions"]) == {
        "market_researcher",
        "fact_checker",
        "market_analyst",
        "market_strategist",
        "report_writer",
    }
    market = report["market"]
    assert market["scope"] == {"product": "Fresh packaged milk", "region": "Kerala", "customer_type": "households"}
    assert [(f["force"], f["rating"]) for f in market["forces"]] == [("rivalry", "high"), ("entry_barriers", "high")]
    assert [i["text"] for i in market["signals_for"]] == ["Demand grew 6% a year."]
    assert [i["text"] for i in market["signals_against"]] == ["Milma controls collection."]
    assert market["checks_before_investing"] == [
        "Ask 3 distributors in Kochi their margin",
        "Confirm the FSSAI licence cost",
    ]
    assert "not financial advice" in market["disclaimer"]
    assert report["swot"] == {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}
    overview = report["company_overview"]
    assert overview["name"] == "Fresh packaged milk in Kerala" and overview["website"] is None
    assert overview["identity"]["text"].startswith("Covers packaged fresh milk")
    assert [g["label"] for g in overview["facts"]][:3] == ["Market size", "Growth", "Customers and demand"]
    assert [c["name"] for c in report["competitor_landscape"]] == ["Milma", "Amul"]
    assert report["recommendations"][0]["title"] == "Start with a premium A2 milk brand in Kochi"
    assert report["industry_overview"]["claims"][0]["text"].startswith("Demand for A2")
    writer = prompt_payload(openai.requests_for("ReportNarrative")[0])
    assert writer["mode"] == "market" and writer["checks_before_investing"] and writer["signals_for"]
    assert writer["not_found_in_public_sources"] == ["Costs and margins"]
    estimates = [c for c in writer["claims_you_may_cite"] if c.get("estimate")]
    assert [c["claim"] for c in estimates] == ["IMARC estimates the Kerala dairy market at ₹70,610 crore in 2025."]
    analyst = prompt_payload(openai.requests_for("MarketAnalysisFindings")[0])
    assert [c["claim"] for c in analyst["claims"] if c.get("estimate")] == [estimates[0]["claim"]]
    size = next(g for g in overview["facts"] if g["label"] == "Market size")["claims"]
    assert [c["estimate"] for c in size] == [False, True]
    assert market["not_found"] == ["Costs and margins"]
    assert "Left out player Jeeva: fewer than 2 confirmed facts found." in report["validation"]["warnings"]
    assert "Jeeva" not in {c["name"] for c in report["competitor_landscape"]}
    assert listed["mode"] == "market"
    assert run.mode == "market" and run.scope["region"] == "Kerala" and run.company_id is None
    assert companies == 0  # a market is not a company


async def test_a_market_run_without_analysis_is_partial(tmp_path: Path):
    script = market_script()
    script["MarketAnalysisFindings"] = [500]
    async with api(tmp_path, openai=FakeOpenAI(script), tavily=milk_tavily()) as (client, _):
        run_id = (await client.post(API, json=MILK)).json()["id"]
        detail = await wait_until_finished(client, run_id)
        report = (await client.get(f"{API}/{run_id}/report")).json()
    assert detail["status"] == "partial"
    assert report["meta"]["mode"] == "market" and report["market"]["forces"] == []
    assert report["market"]["checks_before_investing"] == []
    assert "swot" in report["meta"]["missing_sections"] and "recommendations" in report["meta"]["missing_sections"]


async def test_market_requests_are_validated(tmp_path: Path):
    cases = [
        ({"query": "Milk", "mode": "market"}, "needs the product and region"),
        ({**MILK, "market": {"product": "Milk", "region": " "}}, "Enter the region"),
        ({**MILK, "market": {"product": "x", "region": "Kerala"}}, "Enter the product"),
        ({**MILK, "company": {"name": "Milma"}}, "not a company or competitors"),
        ({**MILK, "competitors": [{"name": "Milma"}]}, "not a company or competitors"),
    ]
    async with api(tmp_path) as (client, _):
        for body, message in cases:
            response = await client.post(API, json=body)
            assert response.status_code == 422 and message in str(response.json()), body
        ok = await client.post(
            API, json={**MILK, "market": {"product": "Milk", "region": "Global", "customer_type": " "}}
        )
    assert ok.status_code == 202


def test_thin_players_are_left_out_with_their_claims():
    findings = MarketFindings.model_validate(market_findings())
    sources = [SourceCreate(url=u, retrieved_by="search") for u in (STATS, NEWS, MILMA, "https://amul.com")]
    claims = extract_claims(dedupe_findings(findings), sources)
    verdicts = [
        ClaimVerdict(
            claim_id=c.id, verdict="supported", confidence="high", reason="ok", supporting_urls=[], source_year=None
        )
        for c in claims
    ]
    checked = merge_verdicts(claims, verdicts, sources)
    kept_findings, kept, notes = drop_thin_players(dedupe_findings(findings), checked)
    assert [p.name for p in kept_findings.players] == ["Milma", "Amul"]
    assert notes == ["Left out player Jeeva: fewer than 2 confirmed facts found."]
    assert not any(c.subject == "Jeeva" for c in kept) and len(kept) == len(checked) - 2
