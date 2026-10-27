"""The M10 benchmark's scoring and results page (the live runner itself is not unit-tested)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.agno_db import build_agno_db
from schemas.report import Report
from schemas.research import SourceCreate
from tests.conftest import make_settings
from tests.fakes import (
    FakeOpenAI,
    FakeTavily,
    analysis_for,
    fact_checker_echo,
    narrative_for,
    sample_findings,
    strategy_for,
    tool_call,
)
from tests.live.benchmark import (
    CountingTavily,
    RunResult,
    all_claims,
    criteria,
    load_saved,
    results_markdown,
    sample_supported,
    save_run,
    score,
    slug,
)
from workflow.claims import extract_claims
from workflow.research_workflow import build_research_workflow, outcome_from_run

SOURCE = "https://www.notion.com"


@pytest.fixture
async def report(tmp_path) -> Report:
    ids = [c.id for c in extract_claims(sample_findings(), [SourceCreate(url=SOURCE, retrieved_by="search")])]
    openai = FakeOpenAI(
        {
            "ResearchFindings": [[tool_call("search_web", query="Notion")], sample_findings()],
            "ValidationResult": [fact_checker_echo({"C2": "unsupported"})],
            "AnalysisFindings": [analysis_for("Notion", "Coda", ids)],
            "StrategyRecommendations": [strategy_for(["F1", "F2", "F5"])],
            "ReportNarrative": [narrative_for("C1")],
        }
    )
    tavily = FakeTavily(search_results={"Notion": [{"url": SOURCE + "/", "title": "Notion", "content": "Workspace"}]})
    settings = make_settings(tmp_path, openai_api_key="sk-test", tavily_api_key="tvly-test")
    workflow = build_research_workflow(
        settings, build_agno_db(settings), http_client=openai.client, tavily_client=tavily
    )
    result = outcome_from_run(await workflow.arun(input="Notion", session_id="s1", additional_data={}))
    assert result.report is not None
    return result.report


async def test_counting_tavily_counts_requests_and_credits():
    tavily = CountingTavily(FakeTavily(pages={"https://a.example": "A"}))
    await tavily.search("Notion")
    await tavily.extract(["https://a.example"])
    await tavily.extract([f"https://{n}.example" for n in range(6)])  # 6 URLs → 2 credits
    assert (tavily.searches, tavily.extracts, tavily.credits) == (1, 2, 4)


def test_score_and_sample(report: Report):
    claims = all_claims(report)
    assert claims[0][1] == "Identity" and {s for s, _, _ in claims} >= {"Notion", "Coda", "Industry"}

    sample = sample_supported(report, n=3)
    assert len(sample) == 3 and all(c.verdict == "supported" for _, _, c in sample)
    assert sample == sample_supported(report, n=3)  # same report → same sample
    assert len(sample_supported(report, n=100)) == sum(1 for _, _, c in claims if c.verdict == "supported")

    tavily = {"searches": 3, "extracts": 1, "credits": 4}
    row = score(RunResult("Notion", "succeeded", 61.4, report, tavily=tavily))
    assert row["company"] == "Notion" and row["competitors"] == ["Coda", "Confluence"]
    assert row["sections"] == 12 and row["seconds"] == 61 and row["credits"] == 4
    assert row["unconfirmed"] == 1 and 0 < row["supported_pct"] < 100
    assert row["unflagged_unsourced"] == 0 and row["incomplete_recommendations"] == 0


def test_criteria(report: Report):
    good = score(RunResult("Notion", "succeeded", 60, report))
    failed = score(RunResult("Acme", "failed", 5, None, "Researcher timed out"))
    statuses = [s for _, _, s in criteria([good, good, good, good, failed])]
    assert statuses == ["PASS", "CHECK", "PASS", "CHECK", "PASS"]  # only 2 competitors → criterion 3 needs a look

    broken = {**good, "unflagged_unsourced": 2, "incomplete_recommendations": 1}
    statuses = [s for _, _, s in criteria([broken, failed, failed])]
    assert statuses == ["FAIL", "CHECK", "FAIL", "CHECK", "FAIL"]


def test_results_page(report: Report):
    results = [
        RunResult("Notion", "succeeded", 60, report, tavily={"searches": 3, "extracts": 1, "credits": 4}),
        RunResult(
            "Acme | Ltd", "failed", 5, None, "Researcher timed out", {"searches": 1, "extracts": 0, "credits": 1}
        ),
    ]
    page = results_markdown(results, datetime(2026, 10, 26, 12, 0, tzinfo=UTC))
    assert page.startswith("# Delphi Market360 — POC benchmark results")
    assert "| Notion | succeeded | Notion | Coda, Confluence |" in page
    assert "| Acme \\| Ltd | **failed** |" in page and "- Acme \\| Ltd: Researcher timed out" in page
    assert "Average per report: 60 s" in page
    assert "### Notion (`Notion`)" in page and f"]({SOURCE})" in page
    assert page.count("Correct: __ / 10") == 1 and "## Decision" in page


def test_slug():
    assert slug("https://monzo.com") == "https-monzo-com" and slug("Notion") == "notion"


def test_save_and_rebuild_from_saved(report: Report, tmp_path):
    tavily = {"searches": 3, "extracts": 1, "credits": 4}
    save_run(tmp_path, RunResult("https://monzo.com", "succeeded", 87.2, report, tavily=tavily))
    save_run(tmp_path, RunResult("Acme", "failed", 5, None, "Researcher timed out", tavily))  # no report: skipped
    # An older run saved only its report (no run-*.json): time from step durations, Tavily not recorded
    (tmp_path / "report-notion.json").write_text(report.model_dump_json(), encoding="utf-8")

    results = load_saved(tmp_path)
    assert [r.query for r in results] == ["Notion", "https://monzo.com"]  # benchmark order
    old, new = results
    assert old.tavily == {} and old.seconds == sum(u.duration_ms or 0 for u in report.meta.usage) / 1000
    assert (new.seconds, new.tavily, new.outcome) == (87.2, tavily, "succeeded")

    page = results_markdown(results, datetime(2026, 10, 26, tzinfo=UTC))
    assert "| not recorded |" in page and "| 4 (4) |" in page
    assert "4 Tavily credits" in page  # the average uses only runs that recorded credits


def test_average_without_any_tavily_numbers(report: Report):
    page = results_markdown([RunResult("Notion", "succeeded", 60, report)], datetime(2026, 10, 26, tzinfo=UTC))
    assert "Average per report: 60 s" in page and "Tavily credits" not in page


def test_second_round_summary(report: Report):
    from schemas.report import SecondRoundOut

    with_round = report.model_copy(
        update={"meta": report.meta.model_copy(update={"second_round": SecondRoundOut(gaps=["a", "b"], filled=1)})}
    )
    results = [RunResult("Notion", "succeeded", 70, with_round), RunResult("Monzo", "succeeded", 70, report)]
    md = results_markdown(results, datetime(2026, 10, 27, tzinfo=UTC))
    assert "Second research round (M14) ran in 1 of 2 reports: 1 of 2 gaps filled." in md
    assert "Research step (M15: lead + competitors in parallel):" in md


def test_research_numbers_add_the_parallel_competitors(report: Report):
    from schemas.report import StepUsageOut
    from tests.live.benchmark import research_numbers

    usage = [
        StepUsageOut(step="research", agent_version="lead@1", model="m", total_tokens=30000, duration_ms=20000),
        StepUsageOut(step="competitors", agent_version="competitor_researcher@1", model="m", total_tokens=12000,
                     duration_ms=15000),
        StepUsageOut(step="validate", agent_version="fact_checker@4", model="m", total_tokens=9000, duration_ms=9000),
    ]  # fmt: skip
    r = report.model_copy(update={"meta": report.meta.model_copy(update={"usage": usage})})
    assert research_numbers(r) == (35, 42000)
