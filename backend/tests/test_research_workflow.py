"""The full five-step workflow as AgentOS runs it: in the background, stored by Agno, read back by run id.

OpenAI and Tavily are fakes; everything else (Agno, our steps, checks and the assembler) is real.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from agno.workflow import Condition, Step

import workflow.research_workflow as wf_module
from core.agno_db import build_agno_db
from core.config import Settings
from schemas.research import SourceCreate
from tests.conftest import make_settings
from tests.fakes import (
    FakeOpenAI,
    FakeTavily,
    analysis_for,
    fact_checker_echo,
    narrative_for,
    prompt_payload,
    sample_findings,
    strategy_for,
    tool_call,
)
from workflow.claims import extract_claims
from workflow.research_workflow import (
    STEP_NAMES,
    WORKFLOW_ID,
    RunOutcome,
    build_research_workflow,
    outcome_from_run,
    usage_from,
)

SESSION = "11111111-1111-1111-1111-111111111111"  # = research run id in Milestone 7
SOURCE = "https://www.notion.com"
CLAIM_IDS = [c.id for c in extract_claims(sample_findings(), [SourceCreate(url=SOURCE, retrieved_by="search")])]

# M14: the optional second round sits between validate and analyse (an Agno Condition, always listed)
WITH_CONDITION = ["research", "validate", "research_more", "analyse", "strategise", "write"]


@pytest.fixture
def keyed_settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path, openai_api_key="sk-test", tavily_api_key="tvly-test")


def happy_script(**overrides) -> dict[str, list]:
    script = {
        "ResearchFindings": [[tool_call("search_web", query="Notion")], sample_findings()],
        "ValidationResult": [fact_checker_echo()],
        "AnalysisFindings": [analysis_for("Notion", "Coda", CLAIM_IDS)],
        "StrategyRecommendations": [strategy_for(["F1", "F2", "F5"])],
        "ReportNarrative": [narrative_for("C2")],
    }
    script.update(overrides)
    return script


def notion_tavily() -> FakeTavily:
    return FakeTavily(search_results={"Notion": [{"url": SOURCE + "/", "title": "Notion", "content": "Workspace"}]})


async def run_workflow(
    settings: Settings,
    openai: FakeOpenAI,
    tavily: FakeTavily | None = None,
    query: str = "Notion",
    progress=None,
    **additional,
) -> tuple[object, RunOutcome]:
    """Start in the background like AgentOS does, poll until finished — the pattern the API will use."""
    workflow = build_research_workflow(
        settings,
        build_agno_db(settings),
        http_client=openai.client,
        tavily_client=tavily or notion_tavily(),
        progress=progress,
    )
    started = await workflow.arun(input=query, session_id=SESSION, additional_data=additional, background=True)
    for _ in range(200):
        await asyncio.sleep(0.05)
        run = await workflow.aget_run(started.run_id, session_id=SESSION)
        if run is not None and str(getattr(run.status, "value", run.status)) in ("COMPLETED", "ERROR"):
            return run, outcome_from_run(run)
    raise AssertionError("workflow did not finish")


async def test_happy_path_produces_a_complete_sourced_report(keyed_settings: Settings):
    calls: list[tuple[str, str]] = []

    async def progress(research_id: str, step: str) -> None:
        calls.append((research_id, step))

    openai = FakeOpenAI(happy_script())
    run, result = await run_workflow(keyed_settings, openai, progress=progress, research_id=SESSION)

    assert [s.step_name for s in run.step_results] == WITH_CONDITION
    assert calls == [(SESSION, step) for step in STEP_NAMES]
    assert result.outcome == "succeeded" and result.error is None
    report = result.report
    assert report.meta.outcome == "succeeded" and report.meta.missing_sections == []
    assert set(report.meta.agent_versions) == {"researcher", "fact_checker", "analyst", "strategist", "report_writer"}
    assert [u.step for u in report.meta.usage] == list(STEP_NAMES)
    assert report.meta.total_tokens == sum(u.total_tokens for u in report.meta.usage) > 0

    # Sources and references
    assert [(r.ref, r.url) for r in report.references] == [(1, SOURCE)]
    assert report.company_overview.website == "https://www.notion.com"
    assert report.company_overview.identity.refs == [1]
    assert {g.label for g in report.company_overview.facts} >= {"Description", "Industry", "Products and services"}
    assert [c.name for c in report.competitor_landscape] == ["Coda", "Confluence"]

    # Validation: every claim checked by the fact-checker, all supported
    assert report.validation.claims_total == len(CLAIM_IDS) == report.validation.supported

    # Analysis: invented evidence dropped, insights numbered, refs attached
    assert [i.text for i in report.swot.threats] == ["Crowded market."]
    assert any("Invented threat" in w for w in report.validation.warnings)
    assert report.swot.strengths[0].id == "F1" and report.swot.strengths[0].refs == [1]
    assert report.competitive_comparison[0].cells[0].refs == [1]
    assert report.market_trends and report.opportunities and report.risks

    # Recommendations: renumbered by priority, the one without evidence dropped
    assert [(r.priority, r.title) for r in report.recommendations] == [(1, "First"), (2, "Second"), (3, "Third")]
    assert report.recommendations[0].evidence_ids == ["F1", "C1"]
    assert any("No evidence" in w for w in report.validation.warnings)

    # Prose: [C2] became [1]; the unknown [C999] was removed
    assert report.executive_summary == "Notion is a connected workspace [1]. Unknown ref."
    assert report.industry_overview.text == "The market is crowded [1]."
    assert report.next_steps == ["Ship AI features", "Target enterprises"]


async def test_contradicted_claims_are_removed_before_analysis(keyed_settings: Settings):
    openai = FakeOpenAI(happy_script(ValidationResult=[fact_checker_echo({"C3": "contradicted"})]))
    _, result = await run_workflow(keyed_settings, openai)

    analyst_claims = [c["id"] for c in prompt_payload(openai.requests_for("AnalysisFindings")[0])["claims"]]
    assert "C3" not in analyst_claims and "C2" in analyst_claims
    assert result.report.validation.contradicted == 1
    assert any(w.startswith("Removed C3") for w in result.report.validation.warnings)


async def test_claims_citing_unretrieved_pages_are_judged_in_code(keyed_settings: Settings):
    findings = sample_findings(source_url="https://never-retrieved.example")
    openai = FakeOpenAI(
        happy_script(ResearchFindings=[[tool_call("search_web", query="Notion")], findings], ValidationResult=[])
    )
    _, result = await run_workflow(keyed_settings, openai)

    assert openai.requests_for("ValidationResult") == []  # nothing worth paying an LLM to check
    v = result.report.validation
    assert v.unsupported == v.claims_total == len(CLAIM_IDS)
    assert any("never retrieved" in w for w in v.warnings)
    # Nothing was retrieved, so no insight or recommendation has a source behind it: all dropped
    assert result.report.swot.strengths == [] and result.report.recommendations == []
    assert any("no retrieved source" in w for w in v.warnings)


async def test_cited_but_unread_pages_are_fetched_by_code_and_fact_checked(keyed_settings: Settings):
    unread = "https://coda.io"
    findings = sample_findings()
    comp = findings.competitors[0]
    cited = comp.description.model_copy(update={"source_urls": [unread]})
    findings = findings.model_copy(update={"competitors": [comp.model_copy(update={"description": cited})]})
    tavily = notion_tavily()
    tavily.pages[unread] = "Coda is an all-in-one doc for teams."
    openai = FakeOpenAI(happy_script(ResearchFindings=[[tool_call("search_web", query="Notion")], findings]))
    _, result = await run_workflow(keyed_settings, openai, tavily)

    assert ("extract", [unread]) in tavily.calls  # one batched fetch, no LLM tokens
    checked_sources = prompt_payload(openai.requests_for("ValidationResult")[0])["sources"]
    assert unread in checked_sources  # the Fact-Checker judged the real page text
    assert unread in {r.url for r in result.report.references}
    assert any("fetched by code for fact-checking" in w for w in result.report.validation.warnings)


async def test_analyst_failure_gives_a_partial_report(keyed_settings: Settings):
    openai = FakeOpenAI(happy_script(AnalysisFindings=["not valid JSON"]))
    run, result = await run_workflow(keyed_settings, openai)

    assert [s.step_name for s in run.step_results] == WITH_CONDITION  # later steps still ran
    assert result.outcome == "partial"
    meta = result.report.meta
    assert set(meta.step_errors) == {"analyse", "strategise", "write"}
    assert {"swot", "recommendations", "executive_summary"} <= set(meta.missing_sections)
    assert result.report.company_overview.facts  # research + validation are still in the report
    assert openai.requests_for("StrategyRecommendations") == []  # no paid calls without analysis
    assert openai.requests_for("ReportNarrative") == []


async def test_writer_failure_still_gives_report_without_prose(keyed_settings: Settings):
    openai = FakeOpenAI(happy_script(ReportNarrative=["oops"]))
    _, result = await run_workflow(keyed_settings, openai)

    assert result.outcome == "partial"
    assert result.report.executive_summary == "" and result.report.next_steps == []
    assert result.report.meta.missing_sections == ["executive_summary", "next_steps"]
    assert len(result.report.recommendations) == 3


async def test_strategist_failure_gives_partial_report(keyed_settings: Settings):
    openai = FakeOpenAI(happy_script(StrategyRecommendations=["oops"]))
    _, result = await run_workflow(keyed_settings, openai)
    assert result.outcome == "partial"
    assert result.report.meta.missing_sections == ["recommendations"]
    assert "strategise" in result.report.meta.step_errors


async def test_fact_check_failure_stops_the_run(keyed_settings: Settings):
    openai = FakeOpenAI(happy_script(ValidationResult=["oops"]))
    run, result = await run_workflow(keyed_settings, openai)
    assert [s.step_name for s in run.step_results] == ["research", "validate"]
    assert (result.outcome, result.failed_step, result.report) == ("failed", "validate", None)
    assert result.error.startswith("Fact-checking failed: Fact-Checker returned no valid output")
    assert openai.requests_for("AnalysisFindings") == []


async def test_research_failure_stops_the_run_without_calling_openai(keyed_settings: Settings):
    openai = FakeOpenAI({})
    _, result = await run_workflow(keyed_settings, openai, query="   ")
    assert (result.outcome, result.failed_step) == ("failed", "research")
    assert "No company" in result.error
    assert openai.requests == []


async def test_invalid_research_output_fails_once_without_agno_retries(keyed_settings: Settings):
    openai = FakeOpenAI(happy_script(ResearchFindings=["not JSON for the schema"]))
    _, result = await run_workflow(keyed_settings, openai)
    assert result.outcome == "failed" and "no valid findings" in result.error
    assert len(openai.requests) == 1  # max_retries=0: no hidden repeated (paid) calls


async def test_research_timeout(keyed_settings: Settings, monkeypatch: pytest.MonkeyPatch):
    async def never_finishes(self, *args, **kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(wf_module, "RESEARCHER", SimpleNamespace(**{**vars(wf_module.RESEARCHER), "timeout_s": 0.05}))
    monkeypatch.setattr("agno.agent.Agent.arun", never_finishes)
    _, result = await run_workflow(keyed_settings, FakeOpenAI({}))
    assert "timed out" in result.error


async def test_research_crash(keyed_settings: Settings, monkeypatch: pytest.MonkeyPatch):
    async def explode(self, *args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("agno.agent.Agent.arun", explode)
    _, result = await run_workflow(keyed_settings, FakeOpenAI({}))
    assert "RuntimeError: boom" in result.error


async def test_later_agent_timeout_and_crash_give_partial(keyed_settings: Settings, monkeypatch: pytest.MonkeyPatch):
    original = wf_module.build_agent

    def patched(spec, *args, **kwargs):
        agent = original(spec, *args, **kwargs)
        if spec.key == "analyst":

            async def crash(*a, **k):
                raise RuntimeError("analyst exploded")

            agent.arun = crash
        return agent

    monkeypatch.setattr(wf_module, "build_agent", patched)
    _, result = await run_workflow(keyed_settings, FakeOpenAI(happy_script()))
    assert result.outcome == "partial"
    assert "RuntimeError: analyst exploded" in result.report.meta.step_errors["analyse"]


async def test_website_input_and_broken_progress_callback(keyed_settings: Settings):
    async def broken_progress(research_id: str, step: str) -> None:
        raise RuntimeError("db down")

    openai = FakeOpenAI(happy_script())
    _, result = await run_workflow(
        keyed_settings,
        openai,
        query="notion.so",
        progress=broken_progress,
        research_id=SESSION,
        website_url="https://notion.so",
    )
    assert result.outcome == "succeeded"  # a broken progress callback never breaks a run
    assert "https://notion.so" in str(openai.requests_for("ResearchFindings")[0]["messages"][-1]["content"])


async def test_event_loop_stays_free_during_web_search(keyed_settings: Settings):
    """Slow searches must not freeze the API (why we use async Tavily instead of Agno's sync TavilyTools)."""

    class SlowTavily(FakeTavily):
        async def search(self, query, **kwargs):
            await asyncio.sleep(0.5)
            return {"results": []}

    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    try:
        await run_workflow(keyed_settings, FakeOpenAI(happy_script()), SlowTavily())
    finally:
        beat.cancel()
    assert ticks >= 8  # ~10 ticks during the 0.5 s search; a blocked loop would give ~0


def test_workflow_shape(keyed_settings: Settings):
    workflow = build_research_workflow(keyed_settings, None)
    assert workflow.id == WORKFLOW_ID
    assert [s.name for s in workflow.steps] == WITH_CONDITION
    steps = [s for s in workflow.steps if isinstance(s, Step)]
    steps += [inner for s in workflow.steps if isinstance(s, Condition) for inner in s.steps]
    assert len(steps) == 6 and all(s.max_retries == 0 for s in steps)  # no hidden paid retries, also inside


def test_outcome_without_any_steps():
    result = outcome_from_run(SimpleNamespace(step_results=[], status="ERROR"))
    assert result.outcome == "failed" and "without a report" in result.error


def test_usage_handles_missing_metrics():
    usage = usage_from(SimpleNamespace(metrics=None, tools=None), agent_version="researcher@3", model="m")
    assert (usage.total_tokens, usage.tool_calls, usage.duration_ms) == (0, 0, None)
