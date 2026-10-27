"""M15: the lead researcher plus one small researcher per competitor / market player, running at the same time
(fake OpenAI and Tavily)."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agents.competitor_researcher import COMPETITOR_RESEARCHER, build_competitor_prompt
from agents.market import MARKET_LEAD, MARKET_RESEARCHER
from agents.researcher import LEAD_RESEARCHER, RESEARCHER, build_research_prompt
from schemas.findings import Competitor
from services.research_service import build_steps
from tests.conftest import make_settings
from tests.fakes import FakeOpenAI, FakeTavily, tool_call
from tests.test_m13_market import MILK, MILMA, market_script, milk_tavily
from tests.test_research_api import API, api, wait_until_finished
from tests.test_research_workflow import happy_script, notion_tavily, run_workflow
from workflow.claims import merge_competitor
from workflow.research_workflow import confirmed_pick

CODA_PRICING = "https://coda.io/pricing"


def profile(name: str, site: str, price: str | None = None) -> dict[str, Any]:
    def s(text: str, url: str = site) -> dict[str, Any]:
        return {"text": text, "source_urls": [url], "kind": "fact"}

    return {
        "name": name,
        "website": site + "/",
        "relation": "direct",
        "description": s(f"{name} is a collaborative docs product."),
        "offerings": [s(f"{name} offers docs and wikis.")],
        "pricing": s(price, CODA_PRICING) if price else None,
        "target_segments": [s("Product teams.")],
        "positioning": None,
    }


def competitor_researcher(answers: dict[str, Any]) -> Any:
    """Answers per competitor (read from the prompt); first turn reads the homepage, second turn answers.
    An int answer = that HTTP error (the researcher fails)."""

    def answer(body: dict[str, Any]) -> Any:
        user = next(m["content"] for m in body["messages"] if m.get("role") == "user")
        name = re.match(r"Profile the company (.+?) \(", str(user)).group(1)
        reply = answers[name]
        if isinstance(reply, int):
            return reply
        if not any(m.get("role") == "tool" for m in body["messages"]):
            return [tool_call("read_webpage", url=reply["website"])]
        return reply

    return [answer] * 20


def parallel_tavily() -> FakeTavily:
    tavily = notion_tavily()
    tavily.pages.update(
        {
            "https://coda.io/": "Coda: docs and wikis for product teams. Pro costs $10 per doc maker per month.",
            "https://confluence.com/": "Confluence team wiki.",
        }
    )
    return tavily


# --- specs and prompts -----------------------------------------------------------------------------------


def test_lead_and_competitor_specs():
    assert LEAD_RESEARCHER.key == RESEARCHER.key and LEAD_RESEARCHER.version == "lead_researcher@1"
    assert LEAD_RESEARCHER.tool_call_limit == 10 and RESEARCHER.tool_call_limit == 15
    lead = " ".join(LEAD_RESEARCHER.instructions)
    assert "Separate researchers profile each competitor in detail" in lead and "PLAN (at most 10" in lead
    assert "read each competitor's homepage" not in lead
    market = " ".join(MARKET_LEAD.instructions)
    assert MARKET_LEAD.key == MARKET_RESEARCHER.key and "Do not read players' websites yourself" in market
    assert COMPETITOR_RESEARCHER.output_schema is Competitor and COMPETITOR_RESEARCHER.tool_call_limit == 4
    assert build_competitor_prompt("Coda", None, "direct", against="Notion") == (
        "Profile the company Coda (website unknown: find it). relation: direct. It is a direct competitor of Notion."
    )
    assert "main players in this market: Milk in Kerala" in build_competitor_prompt(
        "Milma", "https://milma.com", "direct", against="Milk in Kerala", market=True
    )
    confirmed = build_research_prompt("Notion", competitors=[{"name": "Coda"}], parallel=True)
    assert "profiled separately. Do not research competitors." in confirmed and "1. Coda" not in confirmed


def test_strict_schemas_for_the_new_agents():
    from agno.utils.models.schema_utils import get_response_schema_for_provider

    from tests.test_output_schemas import strict_schema_problems

    for spec in (LEAD_RESEARCHER, MARKET_LEAD, COMPETITOR_RESEARCHER):
        assert strict_schema_problems(get_response_schema_for_provider(spec.output_schema, "openai")) == []


def test_merge_keeps_the_picks_name_and_adds_the_profile():
    pick = Competitor.model_validate({**profile("Coda", "https://coda.io"), "name": "Coda (Superhuman)"})
    found = Competitor.model_validate(profile("Coda", "https://www.coda.io/products", price="Pro: $10 a month."))
    merged = merge_competitor(pick, found)
    assert merged.name == "Coda (Superhuman)" and merged.website == "https://www.coda.io"
    assert len(merged.offerings) == 2 and merged.pricing.text == "Pro: $10 a month."
    unsourced = found.model_copy(update={"description": found.description.model_copy(update={"source_urls": []})})
    assert merge_competitor(pick, unsourced).description == pick.description
    placeholder = confirmed_pick({"name": "Coda", "website": "https://coda.io/x"})
    assert placeholder.website == "https://coda.io" and placeholder.description.source_urls == []


def test_progress_while_competitors_are_researched():
    steps = build_steps("competitors", SimpleNamespace(step_results=[]), finished=False)
    assert [(s.name, s.status) for s in steps][:2] == [("research", "running"), ("validate", "pending")]


# --- whole runs ----------------------------------------------------------------------------------------------


async def test_competitors_are_profiled_in_parallel(tmp_path: Path):
    settings = make_settings(
        tmp_path, openai_api_key="sk-test", tavily_api_key="tvly-test", parallel_research_enabled=True
    )
    script = happy_script()
    script["Competitor"] = competitor_researcher(
        {
            "Coda": profile("Coda", "https://coda.io", price="Coda Pro costs $10 per doc maker per month."),
            "Confluence": 500,
        }
    )
    openai = FakeOpenAI(script)
    steps: list[str] = []

    async def progress(_: str, step: str) -> None:
        steps.append(step)

    _, outcome = await run_workflow(settings, openai, parallel_tavily(), progress=progress, research_id="r1")
    report = outcome.report
    assert outcome.outcome == "succeeded", outcome
    assert steps[:2] == ["research", "competitors"]
    lead_system = str(openai.requests_for("ResearchFindings")[0]["messages"][0])
    assert "Separate researchers profile each competitor" in lead_system
    assert len({str(r["messages"][1]) for r in openai.requests_for("Competitor")}) == 2  # one per competitor
    coda = next(c for c in report.competitor_landscape if c.name == "Coda")
    assert any(g.label == "Pricing" for g in coda.facts)
    confluence = next(c for c in report.competitor_landscape if c.name == "Confluence")
    assert [g.label for g in confluence.facts][0] == "Description"  # the lead's line is kept
    assert any(w.startswith("Could not profile Confluence in detail") for w in report.validation.warnings)
    assert [u.step for u in report.meta.usage][:3] == ["research", "competitors", "validate"]
    assert report.meta.agent_versions["researcher"] == "lead_researcher@1"
    assert report.meta.agent_versions["competitor_researcher"] == "competitor_researcher@1"


async def test_confirmed_competitors_are_profiled_without_the_lead(tmp_path: Path):
    settings = make_settings(
        tmp_path, openai_api_key="sk-test", tavily_api_key="tvly-test", parallel_research_enabled=True
    )
    script = happy_script()
    script["Competitor"] = competitor_researcher(
        {"Coda": profile("Coda", "https://coda.io"), "Linear": 500}  # Linear: researcher fails
    )
    openai = FakeOpenAI(script)
    confirmed = [{"name": "Coda", "website": "https://coda.io"}, {"name": "Linear", "website": None}]
    _, outcome = await run_workflow(settings, openai, parallel_tavily(), competitors=confirmed)
    report = outcome.report
    lead_prompt = str(openai.requests_for("ResearchFindings")[0]["messages"])
    assert "profiled separately. Do not research competitors." in lead_prompt
    assert [c.name for c in report.competitor_landscape] == ["Coda"]  # the lead's Confluence is not used
    assert report.meta.missing_competitors == ["Linear"]  # failed and had no sourced facts → missing


async def test_market_players_are_profiled_in_parallel(tmp_path: Path):
    script = market_script()
    script["Competitor"] = competitor_researcher(
        {
            "Milma": {
                **profile("Milma", MILMA, price=None),
                "description": {
                    "text": "Milma is Kerala's milk co-operative.",
                    "source_urls": [MILMA + "/"],
                    "kind": "fact",
                },
            },
            "Amul": profile("Amul", "https://amul.com"),
            "Jeeva": 500,
        }
    )
    tavily = milk_tavily()
    tavily.pages.update(
        {MILMA + "/": "Milma — Kerala Co-operative Milk Marketing Federation.", "https://amul.com/": "Amul."}
    )
    openai = FakeOpenAI(script)
    async with api(tmp_path, openai=openai, tavily=tavily, parallel_research_enabled=True) as (client, _):
        run_id = (await client.post(API, json=MILK)).json()["id"]
        detail = await wait_until_finished(client, run_id)
        report = (await client.get(f"{API}/{run_id}/report")).json()
    assert detail["status"] == "succeeded", detail
    lead_system = str(openai.requests_for("MarketFindings")[0]["messages"][0])
    assert "Do not read players' websites yourself" in lead_system
    prompts = " ".join(str(r["messages"]) for r in openai.requests_for("Competitor"))
    assert "main players in this market: Fresh packaged milk in Kerala" in prompts
    names = [c["name"] for c in report["competitor_landscape"]]
    assert names == ["Milma", "Amul"]  # Jeeva: researcher failed, too thin → left out
    assert report["meta"]["agent_versions"]["market_researcher"] == "market_lead@1"
    usage = {u["step"]: u for u in report["meta"]["usage"]}
    assert usage["competitors"]["agent_version"] == "competitor_researcher@1"
    assert detail["steps"][0]["input_tokens"] >= usage["research"]["input_tokens"]  # step totals include both


async def test_competitor_researchers_run_at_the_same_time(tmp_path: Path):
    """Three researchers that each wait 0.3 s finish in well under 0.9 s."""
    settings = make_settings(
        tmp_path, openai_api_key="sk-test", tavily_api_key="tvly-test", parallel_research_enabled=True
    )
    started: list[float] = []
    loop = asyncio.get_running_loop()

    class SlowTavily(FakeTavily):
        async def extract(self, urls: list[str], **kwargs: Any) -> dict[str, Any]:
            started.append(loop.time())
            await asyncio.sleep(0.3)
            return await super().extract(urls, **kwargs)

    tavily = SlowTavily(search_results=notion_tavily().search_results, pages=parallel_tavily().pages)
    script = happy_script()
    script["Competitor"] = competitor_researcher(
        {"Coda": profile("Coda", "https://coda.io"), "Confluence": profile("Confluence", "https://confluence.com")}
    )
    _, outcome = await run_workflow(settings, FakeOpenAI(script), tavily)
    assert outcome.outcome == "succeeded"
    first_two = sorted(started)[:2]
    assert first_two[1] - first_two[0] < 0.25  # both homepage reads started together, not one after the other


# --- fix round after the first live M15 run (Biscuits · India) ------------------------------------------------


def test_statements_that_only_say_something_is_not_public_are_gaps_not_claims():
    from schemas.findings import MarketFindings
    from schemas.research import SourceCreate
    from tests.test_m13_market import STATS, market_findings
    from workflow.claims import extract_claims

    def s(text: str) -> dict[str, Any]:
        return {"text": text, "source_urls": [STATS], "kind": "fact"}

    findings = MarketFindings.model_validate(
        market_findings(
            costs_margins=[
                s("Publicly available official data on start-up costs is not disclosed by government bodies."),
                s("Margins for biscuit makers are not publicly available."),
            ],
            supply_chain=[s("Branded milk is not available in some rural districts of Kerala.")],  # a real fact
        )
    )
    claims = extract_claims(findings, [SourceCreate(url=STATS, retrieved_by="search")])
    sections = {c.section for c in claims}
    assert "market.costs_margins" not in sections and "market.supply_chain" in sections
    assert [c.id for c in claims] == [f"C{i}" for i in range(1, len(claims) + 1)]  # numbering has no holes


def test_ids_in_any_wording_are_stripped():
    from workflow.report_assembler import strip_ids

    assert (
        strip_ids("Buyers may be less brand-loyal (Implied by F13, F10). Next.")
        == "Buyers may be less brand-loyal. Next."
    )
    assert strip_ids("Thin margins (see C4 and C7).") == "Thin margins."
    assert strip_ids("Costs rise (F2; F14)") == "Costs rise"
    assert strip_ids("Packs of 5 (100 g) sell well (2025).") == "Packs of 5 (100 g) sell well (2025)."  # not ids


def test_players_with_their_own_researcher_are_not_researched_again():
    from schemas.findings import MarketFindings
    from tests.test_m13_market import market_findings
    from workflow.claims import current_year
    from workflow.gaps import find_gaps

    findings = MarketFindings.model_validate(market_findings())
    keys = [g.key for g in find_gaps(findings, [], current_year())]
    assert "player:Milma" in keys and "player:Amul" in keys
    keys = [g.key for g in find_gaps(findings, [], current_year(), profiled=["Milma", "Amul"])]
    assert "player:Milma" not in keys and "player:Amul" not in keys and "player:Jeeva" in keys


async def test_second_round_skips_players_profiled_in_parallel(tmp_path: Path):
    script = market_script()
    script["Competitor"] = competitor_researcher(
        {"Milma": profile("Milma", MILMA), "Amul": profile("Amul", "https://amul.com"), "Jeeva": 500}
    )
    script["ValidationResult"] = script["ValidationResult"] * 2
    script["GapFindings"] = [{"statements": [], "not_found": [1]}]
    tavily = milk_tavily()
    tavily.pages.update({MILMA + "/": "Milma.", "https://amul.com/": "Amul."})
    openai = FakeOpenAI(script)
    async with api(
        tmp_path, openai=openai, tavily=tavily, parallel_research_enabled=True, research_more_enabled=True
    ) as (client, _):
        run_id = (await client.post(API, json=MILK)).json()["id"]
        await wait_until_finished(client, run_id)
    brief = str(openai.requests_for("GapFindings")[0]["messages"])
    assert "Jeeva:" in brief  # its researcher failed: the second round may try it
    assert "about: Milma" not in brief and "about: Amul" not in brief
