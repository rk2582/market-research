"""M14: the research-more loop — gap rules, the round-2 brief and merge, source years and old sources, and
whole runs through the API with the second round on (fake OpenAI and Tavily)."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from db.models.research import ResearchSourceRow
from schemas.findings import ClaimVerdict, GapFindings, MarketFindings
from schemas.report import CheckedClaim, Claim
from schemas.research import SourceCreate
from services.research_service import build_steps
from tests.fakes import FakeOpenAI, prompt_payload, sample_findings, tool_call
from tests.test_m13_market import MILK, MILMA, NEWS, STATS, market_findings, market_script, milk_tavily
from tests.test_research_api import API, api, wait_until_finished
from workflow import research_workflow
from workflow.claims import current_year, merge_verdicts, old_source_year, url_year
from workflow.gaps import MAX_GAPS, Gap, find_gaps, gap_brief, merge_gap_findings

COSTS = "https://agri-finance.example/dairy-plant-costs"
FRESH_PRICES = "https://news.example/2026/05/milk-prices"
OLD_YEAR = 2015


def checked(claim_id: str, subject: str, section: str, label: str, url: str, **extra: Any) -> CheckedClaim:
    values: dict[str, Any] = {
        "id": claim_id,
        "subject": subject,
        "section": section,
        "label": label,
        "text": f"{subject} {label} fact {claim_id}.",
        "kind": "fact",
        "source_urls": [url],
        "verdict": "supported",
        "confidence": "high",
        "reason": "ok",
        "checked_by": "fact_checker",
    }
    values.update(extra)
    return CheckedClaim(**values)


# --- source years and the old-source rule -------------------------------------------------------------


def test_url_year_and_old_source_rule():
    assert url_year("https://finance.example/news/2018/10/kerala-blockchain") == 2018
    assert url_year("https://news.example/kerala-milk-2018-prices") is None  # only /2018/ path parts
    old = checked("C1", "Industry", "industry", "Market trends", NEWS, source_year=2018)
    assert old_source_year(old, 2026) == 2018
    assert old_source_year(old, 2021) is None  # 3 years is not "more than 3"
    founding = checked("C2", "Notion", "company.description", "Description", NEWS, source_year=2010)
    assert old_source_year(founding, 2026) is None  # a description does not go stale
    assert old_source_year(old.model_copy(update={"source_year": None}), 2026) is None


def test_merge_keeps_the_page_year_from_the_checker_or_the_url():
    claims = [
        Claim(id="C1", subject="X", section="industry", label="Market trends", text="a", kind="fact",
              source_urls=["https://site.example/2017/04/a"]),
        Claim(id="C2", subject="X", section="industry", label="Market trends", text="b", kind="fact",
              source_urls=["https://site.example/2017/04/b"]),
    ]  # fmt: skip
    verdicts = [
        ClaimVerdict(claim_id="C1", verdict="supported", confidence="high", reason="ok", supporting_urls=[],
                     source_year=2024),
        ClaimVerdict(claim_id="C2", verdict="supported", confidence="high", reason="ok", supporting_urls=[],
                     source_year=None),
    ]  # fmt: skip
    first, second = merge_verdicts(claims, verdicts)
    assert first.source_year == 2024  # what the page says wins
    assert second.source_year == 2017  # else the year in its URL


# --- gap rules ------------------------------------------------------------------------------------------


def test_company_gaps_pricing_funding_thin_competitor_and_old_sources():
    findings = sample_findings()  # Notion + competitor Coda (coda.io)
    claims = [
        checked("C1", "Notion", "company.description", "Description", "https://www.notion.com"),
        checked("C2", "Coda", "competitor.description", "Description", "https://review.example/coda"),
        checked("C3", "Industry", "industry", "Industry context", "https://news.example/a", source_year=OLD_YEAR),
    ]
    gaps = find_gaps(findings, claims, current_year())
    assert [g.key for g in gaps] == [
        "company:pricing",
        "company:funding",
        "player:Coda",
        "player:Confluence",
        "old:Industry:industry",
    ]
    coda = gaps[2]
    assert coda.ask == "Coda: read its own website (https://coda.io); what it sells and to whom"
    assert gaps[4].fields == ("industry_context",) and "only source is from 2015" in gaps[4].ask
    # an unconfirmed claim does not count; a fresh source next to an old one removes the old-source gap
    claims[0] = claims[0].model_copy(update={"label": "Pricing", "verdict": "unsupported"})
    claims.append(checked("C4", "Industry", "industry", "Industry context", "https://n.example", source_year=2026))
    keys = [g.key for g in find_gaps(findings, claims, 2026)]
    assert "company:pricing" in keys and "old:Industry:industry" not in keys


def test_market_gaps_topics_estimates_players_and_cap():
    findings = MarketFindings.model_validate(market_findings())
    firm = "https://www.imarcgroup.com/kerala-dairy-market"
    claims = [
        checked("C1", findings.market_name, "market.market_size", "Market size", firm),  # an estimate only
        checked("C2", findings.market_name, "market.prices", "Prices", NEWS),
        checked("C3", "Milma", "competitor.description", "Description", MILMA),
        checked("C4", "Milma", "competitor.offerings", "Offerings", MILMA),
        checked("C5", "Milma", "competitor.pricing", "Pricing", MILMA),
    ]
    gaps = find_gaps(findings, claims, current_year())
    keys = [g.key for g in gaps]
    # size first (official figure needed), then players with gaps, then missing topics in importance order
    assert keys == [
        "official:market_size",
        "player:Amul",  # Milma has its own-site facts and a price: no gap
        "player:Jeeva",
        "topic:growth",
        "topic:customers_demand",
        "topic:regulation",
        "topic:barriers",
        "topic:supply_chain",
    ]
    assert len(gaps) == MAX_GAPS  # costs and margins is cut by the cap
    assert (
        gaps[1].ask
        == "Amul: read its own website (https://amul.com/about); what it sells and to whom; its prices per unit"
    )
    assert "find its own website" in gaps[2].ask  # Jeeva has no website
    assert "Fresh packaged milk in Kerala" in gaps[3].ask


def test_brief_lists_numbered_gaps_with_names_and_fields():
    findings = MarketFindings.model_validate(market_findings())
    gaps = [Gap(key="topic:prices", about=findings.market_name, fields=("prices",), ask="Prices: retail prices")]
    brief = gap_brief(gaps, findings, {"product": "Fresh packaged milk", "region": "Kerala"})
    assert brief.startswith("Second research round for: Fresh packaged milk in Kerala (product: Fresh packaged")
    assert "1. about: Fresh packaged milk in Kerala · fields: prices — Prices: retail prices" in brief
    company = sample_findings()
    assert "Second research round for: Notion (https://www.notion.com)." in gap_brief(gaps, company, None)


def test_merge_maps_statements_and_ignores_anything_outside_the_brief():
    findings = sample_findings()
    gaps = [
        Gap(key="company:pricing", about="Notion", fields=("pricing",), ask="Notion: its pricing"),
        Gap(key="player:Coda", about="Coda", fields=("description", "offerings", "pricing", "target_segments",
            "positioning"), ask="Coda: …"),
        Gap(key="old:Industry:industry", about="Industry", fields=("industry_context",), ask="current source"),
    ]  # fmt: skip

    def st(gap: int, about: str, field: str, text: str, url: str, website: str | None = None) -> dict[str, Any]:
        statement = {"text": text, "source_urls": [url], "kind": "fact"}
        return {"gap": gap, "about": about, "field": field, "statement": statement, "website": website}

    found = GapFindings.model_validate(
        {
            "statements": [
                st(
                    1,
                    "Notion",
                    "pricing",
                    "Notion Plus costs $10 per user per month.",
                    "https://www.notion.com/pricing",
                ),
                st(
                    2,
                    "Coda",
                    "pricing",
                    "Coda Pro costs $12 per month.",
                    "https://coda.io/pricing",
                    "https://coda.io/x",
                ),
                st(3, "Industry", "industry_context", "Teams adopt AI workspaces (2026).", "https://n.example/ai"),
                st(1, "Notion", "funding", "Notion raised $10B.", "https://n.example/f"),  # field not in gap 1
                st(9, "Notion", "pricing", "Unknown gap.", "https://n.example/u"),
                st(2, "Coda", "description", "Coda is an all-in-one doc for teams.", "https://coda.io"),  # known
            ],
            "not_found": [],
        }
    )
    sources = [
        SourceCreate(url=u, retrieved_by="search")
        for u in ("https://www.notion.com/pricing", "https://coda.io/pricing")
    ]
    merged = merge_gap_findings(findings, found, gaps, sources, first_id=31)
    assert [(c.id, c.subject, c.section, c.label) for c in merged.claims] == [
        ("C31", "Notion", "company.pricing", "Pricing"),
        ("C32", "Coda", "competitor.pricing", "Pricing"),
        ("C33", "Industry", "industry", "Industry context"),
    ]
    assert merged.claims[2].cited_but_not_retrieved == ["https://n.example/ai"]  # not retrieved → code checks
    assert len(merged.notes) == 2 and all(n.startswith("Second round: ignored") for n in merged.notes)
    assert merged.findings.company.pricing.text.startswith("Notion Plus")  # was empty, now filled
    assert merged.findings.competitors[0].pricing.text == "Coda Pro costs $12 per month."
    assert merged.findings.industry_context[-1].text.startswith("Teams adopt AI")


def test_merge_market_fills_topics_trends_and_a_player_website():
    findings = MarketFindings.model_validate(
        market_findings(players=[{**market_findings()["players"][0], "website": None}])
    )
    gaps = [
        Gap(key="topic:costs_margins", about=findings.market_name, fields=("costs_margins",), ask="costs"),
        Gap(key="player:Milma", about="Milma", fields=("pricing",), ask="Milma: prices"),
        Gap(key="old:Industry:industry", about="Industry", fields=("trends",), ask="current"),
    ]

    def st(gap: int, about: str, field: str, text: str, website: str | None = None) -> dict[str, Any]:
        return {"gap": gap, "about": about, "field": field, "website": website,
                "statement": {"text": text, "source_urls": [COSTS], "kind": "fact"}}  # fmt: skip

    found = GapFindings.model_validate(
        {
            "statements": [
                st(1, findings.market_name, "costs_margins", "A plant costs ₹2 crore."),
                st(2, "Milma", "pricing", "Milma milk is ₹52 a litre.", "https://www.milma.com/products"),
                st(3, "Industry", "trends", "Subscriptions grow."),
            ],
            "not_found": [2],
        }
    )
    merged = merge_gap_findings(findings, found, gaps, [SourceCreate(url=COSTS, retrieved_by="search")], 5)
    assert [(c.section, c.label) for c in merged.claims] == [
        ("market.costs_margins", "Costs and margins"),
        ("competitor.pricing", "Pricing"),
        ("industry", "Market trends"),
    ]
    assert merged.findings.costs_margins[0].text == "A plant costs ₹2 crore."
    assert merged.findings.players[0].website == "https://www.milma.com"  # site root of what it found
    assert merged.findings.trends[-1].text == "Subscriptions grow."


def test_progress_shows_research_running_during_the_second_round():
    steps = build_steps("deepen", SimpleNamespace(step_results=[]), finished=False)
    assert [(s.name, s.status) for s in steps] == [
        ("research", "running"),
        ("validate", "completed"),
        ("analyse", "pending"),
        ("strategise", "pending"),
        ("write", "pending"),
    ]


# --- whole runs through the API ---------------------------------------------------------------------------


def brief_gaps(body: dict[str, Any]) -> dict[str, int]:
    """Gap numbers by `about` (first gap per name), read from the round-2 brief."""
    user = [m for m in body["messages"] if m.get("role") == "user"][-1]["content"]
    found: dict[str, int] = {}
    for number, about, fields in re.findall(r"(\d+)\. about: (.+?) · fields: ([a-z_, ]+) —", user):
        found.setdefault(f"{about}|{fields}", int(number))
    return found


def gap_answer(body: dict[str, Any]) -> dict[str, Any]:
    numbers = brief_gaps(body)

    def number(prefix: str) -> int:
        return next(n for key, n in numbers.items() if key.startswith(prefix))

    def st(gap: int, about: str, field: str, text: str, url: str) -> dict[str, Any]:
        statement = {"text": text, "source_urls": [url], "kind": "fact"}
        return {"gap": gap, "about": about, "field": field, "statement": statement, "website": None}

    market = "Fresh packaged milk in Kerala"
    return {
        "statements": [
            st(number("Milma|"), "Milma", "pricing", "Milma toned milk costs ₹52 per litre.", MILMA + "/"),
            st(
                number(f"{market}|costs_margins"), market, "costs_margins", "A 5,000-litre plant costs ₹2 crore.", COSTS
            ),
            st(
                number(f"{market}|prices"),
                market,
                "prices",
                "Toned milk sold for ₹56 a litre in May 2026.",
                FRESH_PRICES,
            ),
            st(number("Milma|"), "Milma", "funding", "Outside the brief.", MILMA + "/"),
        ],
        "not_found": [number("Amul|")],
    }


def checker(old_text: str | None = None) -> Any:
    def answer(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "verdicts": [
                {
                    "claim_id": c["id"],
                    "verdict": "supported",
                    "confidence": "high",
                    "reason": "ok",
                    "supporting_urls": [],
                    "source_year": OLD_YEAR if old_text and old_text in c["claim"] else None,
                }
                for c in prompt_payload(body)["claims"]
            ]
        }

    return answer


def second_round_script(gap_answers: list[Any]) -> dict[str, list[Any]]:
    script = market_script()
    script["ValidationResult"] = [checker(old_text="₹50 per litre"), checker()]
    script["GapFindings"] = gap_answers
    return script


def second_round_tavily() -> Any:
    tavily = milk_tavily()
    tavily.search_results["Kerala dairy plant cost"] = [
        {"url": COSTS, "title": "Dairy plant costs", "content": "A 5,000-litre plant costs ₹2 crore"}
    ]
    tavily.pages[FRESH_PRICES] = "May 2026: toned milk now sells for ₹56 a litre in Kochi."
    return tavily


async def test_a_market_run_fills_gaps_in_a_second_round(tmp_path: Path):
    script = second_round_script([[tool_call("search_web", query="Kerala dairy plant cost")], gap_answer])
    openai = FakeOpenAI(script)
    tavily = second_round_tavily()
    async with api(tmp_path, openai=openai, tavily=tavily, research_more_enabled=True) as (client, app):
        run_id = (await client.post(API, json=MILK)).json()["id"]
        detail = await wait_until_finished(client, run_id)
        report = (await client.get(f"{API}/{run_id}/report")).json()
        async with app.state.database.session() as session:
            stored = (await session.scalars(select(ResearchSourceRow))).all()

    assert detail["status"] == "succeeded", detail
    brief = str(openai.requests_for("GapFindings")[0]["messages"])
    assert "Find ONLY these gaps" in brief and "Milma: its prices per unit" in brief
    assert "Jeeva: find its own website" in brief  # a thin player is researched before being left out
    meta = report["meta"]
    second = meta["second_round"]
    assert second["error"] is None and second["new_claims"] == 3
    # Milma price, costs, old prices filled; Amul's price and thin Jeeva not (Jeeva is then left out)
    assert second["filled"] == 3 and len(second["gaps"]) == 5
    assert meta["agent_versions"]["gap_researcher"] == "gap_researcher@2"
    assert [u["step"] for u in meta["usage"]] == ["research", "validate", "deepen", "analyse", "strategise", "write"]
    overview = {g["label"]: g["claims"] for g in report["company_overview"]["facts"]}
    assert [c["text"] for c in overview["Costs and margins"]] == ["A 5,000-litre plant costs ₹2 crore."]
    old, fresh = overview["Prices"]
    assert old["old_source_year"] == OLD_YEAR and fresh["old_source_year"] is None
    milma = next(c for c in report["competitor_landscape"] if c["name"] == "Milma")
    assert any(g["label"] == "Pricing" for g in milma["facts"])
    assert report["market"]["not_found"] == []  # costs and margins found in round 2
    warnings = report["validation"]["warnings"]
    assert "Second research round: 5 gap(s), 3 filled, 3 new claim(s)." in warnings
    assert any(w.startswith("Second round: ignored a statement outside the brief") for w in warnings)
    assert report["validation"]["claims_total"] == 19  # 16 + 3 new
    analyst = prompt_payload(openai.requests_for("MarketAnalysisFindings")[0])
    assert any(c.get("old_source") == OLD_YEAR for c in analyst["claims"])
    assert any(c["claim"].startswith("A 5,000-litre plant") for c in analyst["claims"])  # merged evidence
    costs = next(s for s in stored if s.url == COSTS)
    assert costs.excerpt  # the round-2 page is stored with the text it was checked against
    fresh_page = next(s for s in stored if s.url == FRESH_PRICES)
    assert "₹56" in (fresh_page.excerpt or "")  # cited-but-unread page fetched by code


async def test_a_failed_second_round_keeps_the_first_rounds_report(tmp_path: Path):
    openai = FakeOpenAI(second_round_script([500]))
    async with api(tmp_path, openai=openai, tavily=second_round_tavily(), research_more_enabled=True) as (client, _):
        run_id = (await client.post(API, json=MILK)).json()["id"]
        detail = await wait_until_finished(client, run_id)
        report = (await client.get(f"{API}/{run_id}/report")).json()
    assert detail["status"] == "succeeded"
    second = report["meta"]["second_round"]
    assert second["error"].startswith("Gap Researcher") and second["new_claims"] == 0
    assert report["validation"]["claims_total"] == 16  # round 1 only
    assert report["market"]["not_found"] == ["Costs and margins"]
    assert "deepen" not in [u["step"] for u in report["meta"]["usage"]]


async def test_no_gaps_means_no_second_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(research_workflow, "find_gaps", lambda *args: [])
    openai = FakeOpenAI(second_round_script([]))
    async with api(tmp_path, openai=openai, tavily=second_round_tavily(), research_more_enabled=True) as (client, _):
        run_id = (await client.post(API, json=MILK)).json()["id"]
        await wait_until_finished(client, run_id)
        report = (await client.get(f"{API}/{run_id}/report")).json()
    assert openai.requests_for("GapFindings") == []
    assert report["meta"]["second_round"] is None and "gap_researcher" not in report["meta"]["agent_versions"]


async def test_the_second_round_can_be_switched_off(tmp_path: Path):
    openai = FakeOpenAI(second_round_script([]))
    async with api(tmp_path, openai=openai, tavily=second_round_tavily()) as (client, _):  # off in tests
        run_id = (await client.post(API, json=MILK)).json()["id"]
        report = await wait_until_finished(client, run_id)
    assert report["status"] == "succeeded" and openai.requests_for("GapFindings") == []
    assert STATS  # the fixture data is shared with the M13 tests


def test_gap_researcher_schema_is_openai_strict_compatible():
    from agno.utils.models.schema_utils import get_response_schema_for_provider

    from agents.gap_researcher import GAP_RESEARCHER
    from tests.test_output_schemas import strict_schema_problems

    schema = get_response_schema_for_provider(GAP_RESEARCHER.output_schema, "openai")
    assert strict_schema_problems(schema) == []
    assert GAP_RESEARCHER.tool_call_limit == 8 and GAP_RESEARCHER.timeout_s == 120


def test_markdown_shows_old_sources_and_the_second_round():
    from schemas.report import Report, SecondRoundOut
    from tests.live.render import report_to_markdown
    from tests.test_market_check import FIXTURE

    report = Report.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    facts = report.company_overview.facts
    old = facts[0].model_copy(update={"claims": [facts[0].claims[0].model_copy(update={"old_source_year": 2018})]})
    report = report.model_copy(
        update={
            "company_overview": report.company_overview.model_copy(update={"facts": [old, *facts[1:]]}),
            "meta": report.meta.model_copy(
                update={"second_round": SecondRoundOut(gaps=["Milma: prices"], filled=0, error="timed out")}
            ),
        }
    )
    md = report_to_markdown(report)
    assert "_(old source: 2018)_" in md
    assert "Second research round: 0 of 1 gaps filled (failed: timed out)\n  - Milma: prices" in md


def test_estimates_give_way_to_primary_sources():
    from workflow.claims import is_estimate, is_primary_source, primary_hosts

    firm = "https://www.imarcgroup.com/dairy-industry-kerala"
    claim = checked("C1", "Milma", "competitor.description", "Description", firm)
    assert is_estimate(claim)
    own = claim.model_copy(update={"source_urls": [firm, "https://milma.com/about/aboutus"]})
    findings = MarketFindings.model_validate(market_findings())  # Milma's site: https://www.milma.com/about
    assert "milma.com" in primary_hosts(findings)
    assert not is_estimate(own, primary_hosts(findings))  # the company's own site confirms it
    assert is_estimate(own)  # without knowing whose site it is, still an estimate
    for url in (
        "https://dairy.kerala.gov.in/stats",
        "https://mospi.gov.in/x",
        "https://ahd.nic.in/y",
        "https://www.gov.uk/z",
    ):
        assert is_primary_source(url), url
        assert not is_estimate(claim.model_copy(update={"source_urls": [firm, url]}))
    assert not is_primary_source("https://governance-blog.example/a")


def test_round_two_ignores_repeated_figures_and_estimates_offered_as_official():
    findings = MarketFindings.model_validate(market_findings())
    firm = "https://www.imarcgroup.com/dairy-industry-kerala"
    gov = "https://dairy.kerala.gov.in/statistics"
    gaps = [
        Gap(key="official:market_size", about=findings.market_name, fields=("market_size",), ask="official size"),
        Gap(key="topic:growth", about=findings.market_name, fields=("growth",), ask="growth"),
    ]
    existing = [checked("C1", findings.market_name, "market.growth", "Growth", firm,
                        text="IMARC expects 11.97% growth to INR 2,012.3 billion.")]  # fmt: skip

    def st(gap: int, field: str, text: str, url: str) -> dict[str, Any]:
        return {"gap": gap, "about": findings.market_name, "field": field, "website": None,
                "statement": {"text": text, "source_urls": [url], "kind": "fact"}}  # fmt: skip

    found = GapFindings.model_validate(
        {
            "statements": [
                st(1, "market_size", "The market reached INR 706.1 billion per official analysis.", firm),
                st(1, "market_size", "Kerala produced 25.3 lakh tonnes of milk in 2024.", gov),
                st(2, "growth", "The market will grow at 11.97% a year to INR 2,012.3 billion.", firm),
            ],
            "not_found": [],
        }
    )
    sources = [SourceCreate(url=u, retrieved_by="search") for u in (firm, gov)]
    merged = merge_gap_findings(findings, found, gaps, sources, first_id=40, existing=existing)
    assert [c.text for c in merged.claims] == ["Kerala produced 25.3 lakh tonnes of milk in 2024."]
    assert merged.notes[0].startswith("Second round: ignored a research-firm figure offered as official")
    assert merged.notes[1].startswith("Second round: ignored a repeat of an existing figure")
