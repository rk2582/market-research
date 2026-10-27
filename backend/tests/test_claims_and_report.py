"""Claims, the code checks around the Fact-Checker, and the report assembler — including a replay of
the real Notion research from the M5 live run (tests/fixtures/live/notion.json)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from core.agno_db import build_agno_db
from schemas.findings import AnalysisFindings, ClaimVerdict, ResearchFindings, StrategyRecommendations
from schemas.report import REPORT_SECTIONS, AnalysisOut, CheckedClaim, Report
from schemas.research import SourceCreate
from tests.conftest import make_settings
from tests.fakes import (
    FakeOpenAI,
    FakeTavily,
    analysis_for,
    fact_checker_echo,
    narrative_for,
    prompt_payload,
    strategy_for,
    tool_call,
)
from workflow.claims import (
    batches,
    code_verdict,
    extract_claims,
    gate,
    merge_verdicts,
    site_root,
    years_missing_from_sources,
)
from workflow.report_assembler import Evidence, process_analysis, process_recommendations, strip_ids
from workflow.research_workflow import FACT_CHECK_BATCH, build_research_workflow, outcome_from_run
from workflow.source_harvest import clean_title, url_key

FIXTURES = Path(__file__).parent / "fixtures" / "live"


def load_fixture(name: str) -> tuple[ResearchFindings, list[SourceCreate]]:
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return ResearchFindings.model_validate(data["findings"]), [SourceCreate(**s) for s in data["sources"]]


# --- claims ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "root"),
    [
        ("https://www.notion.com/enterprise", "https://www.notion.com"),
        ("https://MONZO.com", "https://monzo.com"),
        ("monzo.com", None),
        ("ftp://x.example/a", None),
        (None, None),
        ("", None),
    ],
)
def test_site_root(url, root):
    assert site_root(url) == root


@pytest.mark.parametrize("name", ["notion", "https-monzo-com"])
def test_real_fixtures_flatten_into_numbered_claims(name: str):
    findings, sources = load_fixture(name)
    claims = extract_claims(findings, sources)
    assert [c.id for c in claims] == [f"C{i}" for i in range(1, len(claims) + 1)]
    assert claims[0].section == "company.identity_note" and claims[0].label == "Identity"
    assert all(c.source_urls for c in claims)  # the M5 live runs cited only retrieved pages
    assert {c.subject for c in claims} >= {findings.company.name, "Industry", findings.competitors[0].name}


def test_http_and_https_count_as_the_same_page():
    findings, _ = load_fixture("https-monzo-com")
    sources = [SourceCreate(url="https://www.cbinsights.com/company/monzo", retrieved_by="search")]
    revolut = [c for c in extract_claims(findings, sources) if c.subject == "Revolut"]
    assert revolut and all(c.source_urls == ["https://www.cbinsights.com/company/monzo"] for c in revolut)


def test_merge_gives_every_claim_exactly_one_verdict():
    findings, sources = load_fixture("https-monzo-com")
    claims = extract_claims(findings, sources)[:3]
    claims[2] = claims[2].model_copy(update={"source_urls": [], "cited_but_not_retrieved": []})
    verdicts = [
        ClaimVerdict(
            claim_id=" C1 ", verdict="supported", confidence="high", reason="ok", supporting_urls=[], source_year=None
        ),
        ClaimVerdict(
            claim_id="C77",
            verdict="contradicted",
            confidence="high",
            reason="unknown id, ignored",
            supporting_urls=[],
            source_year=None,
        ),
    ]
    checked = merge_verdicts(claims, verdicts)
    assert [(c.id, c.verdict, c.checked_by) for c in checked] == [
        ("C1", "supported", "fact_checker"),
        ("C2", "unsupported", "code"),  # not assessed by the model
        ("C3", "unsupported", "code"),  # no source at all
    ]
    assert checked[1].reason == "Not assessed by the fact-checker."
    assert checked[2].reason == "No source was given for this claim."
    assert code_verdict(claims[0].model_copy(update={"cited_but_not_retrieved": ["x"]})).reason.startswith("Cited")


def test_gate_counts_and_removes_contradicted():
    findings, sources = load_fixture("notion")
    claims = extract_claims(findings, sources)[:4]
    verdicts = [
        ClaimVerdict(claim_id=c.id, verdict=v, confidence="medium", reason="r", supporting_urls=[], source_year=None)
        for c, v in zip(claims, ["supported", "partially_supported", "unsupported", "contradicted"], strict=True)
    ]
    kept, summary = gate(merge_verdicts(claims, verdicts))
    assert [c.id for c in kept] == ["C1", "C2", "C3"]
    assert (summary.supported, summary.partially_supported, summary.unsupported, summary.contradicted) == (1, 1, 1, 1)
    assert summary.warnings[0].startswith("Removed C4")


def test_batches():
    assert [len(b) for b in batches(list(range(28)), 25)] == [25, 3]
    assert batches([], 25) == []


# --- assembler edge cases -------------------------------------------------------------------------


def _checked(claim_id: str, verdict: str = "supported") -> CheckedClaim:
    return CheckedClaim(
        id=claim_id,
        subject="X",
        section="company.description",
        label="Description",
        text="t",
        kind="fact",
        source_urls=["https://a.example"],
        verdict=verdict,
        confidence="high",
        reason="r",
        checked_by="fact_checker",
    )


def test_citations_become_reference_numbers():
    evidence = Evidence(
        [_checked("C1"), _checked("C2").model_copy(update={"source_urls": ["http://b.example/"]})],
        [
            SourceCreate(url="https://a.example", retrieved_by="search"),
            SourceCreate(url="https://b.example", retrieved_by="search"),
        ],
    )
    assert evidence.cite("A [C1]. B [C2, C1] and [C1; C9].") == "A [1]. B [1][2] and [1]."
    assert evidence.cite("Only unknown [C9].") == "Only unknown."
    assert evidence.cite("No citations here.") == "No citations here."


def test_repeated_citations_are_merged_and_sorted():
    evidence = Evidence(
        [_checked("C1"), _checked("C2").model_copy(update={"source_urls": ["https://b.example"]})],
        [
            SourceCreate(url="https://a.example", retrieved_by="search"),
            SourceCreate(url="https://b.example", retrieved_by="search"),
        ],
    )
    assert evidence.cite("Monzo [C2][C1][C2][C1][C1].") == "Monzo [1][2]."


def test_only_cited_sources_get_reference_numbers():
    sources = [SourceCreate(url=f"https://{name}.example", retrieved_by="search") for name in ("x", "a", "y", "b")]
    claims = [_checked("C1"), _checked("C2").model_copy(update={"source_urls": ["https://b.example"]})]
    evidence = Evidence(claims, sources)
    assert [s.url for s in evidence.cited_sources] == ["https://a.example", "https://b.example"]
    assert evidence.refs_for_claims(["C1", "C2"]) == [1, 2]


def _insight(text: str, kind: str = "fact") -> dict:
    return {"text": text, "kind": kind, "evidence_claim_ids": ["C1"]}


def _cell(company: str, claim_ids: list[str]) -> dict:
    return {"company": company, "value": "v" if claim_ids else "Not publicly available", "claim_ids": claim_ids}


def test_analysis_drops_thin_comparison_rows_and_downgrades_hedged_facts():
    evidence = Evidence(
        [_checked("C1"), _checked("C2")], [SourceCreate(url="https://a.example", retrieved_by="search")]
    )
    raw = AnalysisFindings.model_validate(
        {
            "comparison": [
                {"dimension": "Pricing", "cells": [_cell("X", ["C1"]), _cell("Y", ["C2"])]},
                {"dimension": "Geography", "cells": [_cell("X", ["C1"]), _cell("Y", []), _cell("Z", [])]},
            ],
            "swot": {
                "strengths": [_insight("Profit rose in May 2026.")],
                "weaknesses": [_insight("The US exit could happen again.")],
                "opportunities": [],
                "threats": [_insight("Rivals might cut prices.", "prediction")],
            },
            "trends": [],
            "opportunities": [],
            "risks": [],
            "data_gaps": [],
            "key_figures": [],
        }
    )
    analysis, warnings = process_analysis(raw, evidence)
    assert [row.dimension for row in analysis.comparison] == ["Pricing"]
    assert any("Geography" in w for w in warnings)
    assert analysis.swot.strengths[0].kind == "fact"  # "May" the month is not a hedge
    assert analysis.swot.weaknesses[0].kind == "interpretation"
    assert analysis.swot.threats[0].kind == "prediction"  # only 'fact' is changed


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        (
            '[Notion, LLC Email Format](/notion-llc-email-format_b44 "Notion, LLC Email Format")',
            "Notion, LLC Email Format",
        ),
        ("  Monzo - Wikipedia ", "Monzo - Wikipedia"),
        ("", None),
        (None, None),
    ],
)
def test_clean_title(raw, clean):
    assert clean_title(raw) == clean


def test_year_not_in_sources_cuts_supported_to_partial():
    findings, sources = load_fixture("notion")
    claims = extract_claims(findings, sources)
    checked = {c.id: c for c in merge_verdicts(claims, fact_checker_echo_verdicts(claims), sources)}
    assert checked["C8"].verdict == "partially_supported"  # "September 2026" — really 2021
    assert checked["C8"].reason.startswith("Year 2026 not found") and checked["C8"].checked_by == "code"
    assert sum(c.verdict == "partially_supported" for c in checked.values()) == 1
    assert years_missing_from_sources(claims[7], []) == ["2026"]  # no sources → every year is missing


def fact_checker_echo_verdicts(claims) -> list[ClaimVerdict]:
    return [
        ClaimVerdict(
            claim_id=c.id, verdict="supported", confidence="high", reason="ok", supporting_urls=[], source_year=None
        )
        for c in claims
    ]


def test_citation_ranges_and_stray_brackets():
    evidence = Evidence(
        [_checked(f"C{n}").model_copy(update={"source_urls": [f"https://{n}.example"]}) for n in (1, 2, 3)],
        [SourceCreate(url=f"https://{n}.example", retrieved_by="search") for n in (1, 2, 3)],
    )
    assert evidence.cite("Bank [C1, C2-C3]. Plans [Recommendations]. Gap [F2, F3].") == "Bank [1][2][3]. Plans. Gap."
    assert evidence.cite("Huge [C1-C99].") == "Huge."  # silly range ignored
    assert strip_ids("Growth is strong (F2, F14). Rivals target SMEs (C8).") == "Growth is strong. Rivals target SMEs."


def test_insights_without_any_retrieved_source_are_dropped_but_unsupported_with_source_downgraded():
    sourced = _checked("C1", "unsupported")
    unsourced = _checked("C2", "unsupported").model_copy(update={"source_urls": []})
    evidence = Evidence([sourced, unsourced], [SourceCreate(url="https://a.example", retrieved_by="search")])
    raw = AnalysisFindings.model_validate(
        {
            "comparison": [],
            "swot": {
                "strengths": [{"text": "Weak fact.", "kind": "fact", "evidence_claim_ids": ["C1"]}],
                "weaknesses": [{"text": "No source.", "kind": "fact", "evidence_claim_ids": ["C2"]}],
                "opportunities": [],
                "threats": [],
            },
            "trends": [],
            "opportunities": [],
            "risks": [],
            "data_gaps": [],
            "key_figures": [],
        }
    )
    analysis, warnings = process_analysis(raw, evidence)
    assert analysis.swot.strengths[0].kind == "interpretation"
    assert analysis.swot.weaknesses == []
    assert any("no retrieved source" in w for w in warnings)


def test_insights_and_recommendations_built_on_missing_data_are_dropped():
    evidence = Evidence([_checked("C1")], [SourceCreate(url="https://a.example", retrieved_by="search")])
    gap = "No evidence was found regarding search capabilities matching Slite."
    raw = AnalysisFindings.model_validate(
        {
            "comparison": [],
            "swot": {
                "strengths": [{"text": "Profit rose.", "kind": "fact", "evidence_claim_ids": ["C1"]}],
                "weaknesses": [{"text": gap, "kind": "interpretation", "evidence_claim_ids": ["C1"]}],
                "opportunities": [],
                "threats": [],
            },
            "trends": [],
            "opportunities": [],
            "risks": [],
            "data_gaps": [],
            "key_figures": [],
        }
    )
    analysis, warnings = process_analysis(raw, evidence)
    assert analysis.swot.weaknesses == [] and len(analysis.swot.strengths) == 1
    assert any("based on missing data" in w for w in warnings)

    drafts = StrategyRecommendations.model_validate(strategy_for(["C1", "C1", "C1"]))
    first = drafts.recommendations[0].model_copy(
        update={"rationale": "Pricing is not publicly available, so publish it."}
    )
    recs, rec_warnings = process_recommendations(
        drafts.model_copy(update={"recommendations": [first, *drafts.recommendations[1:]]}), AnalysisOut(), evidence
    )
    assert first.title not in [r.title for r in recs] and len(recs) == 2  # 4th draft cites an unknown id
    assert any("based on missing data" in w for w in rec_warnings)


def test_too_few_recommendations_is_a_warning():
    evidence = Evidence([_checked("C1")], [SourceCreate(url="https://a.example", retrieved_by="search")])
    raw = StrategyRecommendations.model_validate(strategy_for(["C1", "C1"]))
    recs, warnings = process_recommendations(
        raw.model_copy(update={"recommendations": raw.recommendations[:2]}), AnalysisOut(), evidence
    )
    assert len(recs) == 2 and any("Only 2 recommendation(s)" in w for w in warnings)


# --- replay of the real Notion research through the whole workflow -----------------------------------


def replay_research(findings: ResearchFindings, sources: list[SourceCreate]) -> tuple[FakeTavily, list]:
    """Fake Tavily + Researcher script that return exactly the sources and findings of a live run."""
    searched = [s for s in sources if s.retrieved_by == "search"]
    read = [s for s in sources if s.retrieved_by == "extract"]
    chunks = [searched[i : i + 8] for i in range(0, len(searched), 8)]
    tavily = FakeTavily(
        search_results={
            f"replay-{i}": [{"url": s.url, "title": s.title, "content": s.excerpt} for s in chunk]
            for i, chunk in enumerate(chunks)
        },
        pages={s.url: s.excerpt or "" for s in read},
    )
    script = [
        [tool_call("search_web", query=f"replay-{i}", max_results=8) for i in range(len(chunks))],
        [tool_call("read_webpage", url=s.url) for s in read],
        findings,
    ]
    return tavily, script


async def test_replay_real_notion_run_end_to_end(tmp_path: Path):
    findings, sources = load_fixture("notion")
    claim_ids = [c.id for c in extract_claims(findings, sources)]
    assert len(claim_ids) > FACT_CHECK_BATCH  # forces two fact-check batches, run in parallel

    tavily, research_script = replay_research(findings, sources)
    openai = FakeOpenAI(
        {
            "ResearchFindings": research_script,
            "ValidationResult": [fact_checker_echo({"C8": "contradicted"}), fact_checker_echo({"C8": "contradicted"})],
            "AnalysisFindings": [analysis_for("Notion", "Airtable", claim_ids)],
            "StrategyRecommendations": [strategy_for(["F1", "F2", "F5"])],
            "ReportNarrative": [narrative_for("C2")],
        }
    )
    settings = make_settings(tmp_path, openai_api_key="sk-test", tavily_api_key="tvly-test")
    workflow = build_research_workflow(
        settings, build_agno_db(settings), http_client=openai.client, tavily_client=tavily
    )
    started = await workflow.arun(input="Notion", session_id="replay", background=True)
    for _ in range(200):
        await asyncio.sleep(0.05)
        run = await workflow.aget_run(started.run_id, session_id="replay")
        if run is not None and str(getattr(run.status, "value", run.status)) == "COMPLETED":
            break
    result = outcome_from_run(run)

    assert result.outcome == "succeeded"
    report = Report.model_validate(result.report.model_dump())  # round-trips as plain JSON
    assert len(openai.requests_for("ValidationResult")) == 2
    cited = {url_key(u) for c in extract_claims(findings, sources) if c.id != "C8" for u in c.source_urls}
    assert [r.ref for r in report.references] == list(range(1, len(report.references) + 1))
    assert {url_key(r.url) for r in report.references} == cited  # retrieved-but-unused pages are left out
    assert len(report.references) < len(sources)
    assert report.validation.claims_total == len(claim_ids)
    assert report.validation.contradicted == 1
    # C8 is the live run's misdated "September 2026" Automate.io acquisition — removed from the report
    assert "Automate.io" in report.validation.warnings[0]
    assert all("Automate.io" not in c.text for g in report.company_overview.facts for c in g.claims)
    assert report.company_overview.website == "https://www.notion.com"  # was .../enterprise
    assert [c.name for c in report.competitor_landscape] == ["Airtable", "Asana", "ClickUp", "Coda", "monday.com"]
    every_ref = {r for g in report.company_overview.facts for c in g.claims for r in c.refs}
    assert every_ref and every_ref <= {r.ref for r in report.references}
    assert set(REPORT_SECTIONS) <= set(Report.model_fields) | {"references"}

    # The Markdown used for human review in the live test renders every section without errors
    from tests.live.render import report_to_markdown

    markdown = report_to_markdown(report)
    for heading in ("## 1. Executive summary", "## 5. Competitive comparison", "## 12. References", "## Usage"):
        assert heading in markdown
    partial = report.model_copy(update={"meta": report.meta.model_copy(update={"missing_sections": ["swot"]})})
    assert "Partial report — missing: swot" in report_to_markdown(partial)


async def test_one_failed_fact_check_batch_marks_its_claims_unassessed(tmp_path: Path):
    findings, sources = load_fixture("notion")
    claim_ids = [c.id for c in extract_claims(findings, sources)]
    tavily, research_script = replay_research(findings, sources)

    def fail_second_batch(body):
        ids = [c["id"] for c in prompt_payload(body)["claims"]]
        return 400 if "C26" in ids else fact_checker_echo()(body)

    openai = FakeOpenAI(
        {
            "ResearchFindings": research_script,
            "ValidationResult": [fail_second_batch, fail_second_batch],
            "AnalysisFindings": [analysis_for("Notion", "Airtable", claim_ids)],
            "StrategyRecommendations": [strategy_for(["F1", "F2", "F5"])],
            "ReportNarrative": [narrative_for("C2")],
        }
    )
    settings = make_settings(tmp_path, openai_api_key="sk-test", tavily_api_key="tvly-test")
    workflow = build_research_workflow(
        settings, build_agno_db(settings), http_client=openai.client, tavily_client=tavily
    )
    run = await workflow.arun(input="Notion", session_id="replay-2")
    report = outcome_from_run(run).report

    # C8 (the misdated Automate.io deal) is cut to partial by the code year check
    assert report.validation.supported + report.validation.partially_supported == FACT_CHECK_BATCH
    assert report.validation.unsupported == len(claim_ids) - FACT_CHECK_BATCH
    assert any("1 fact-check batch(es) failed" in w for w in report.validation.warnings)


def test_insight_ids_are_stripped_from_steps_and_risks():
    """Live run (Milk · Kerala, M14): risks read 'squeeze already thin margins (F10).'"""
    evidence = Evidence([_checked("C1")], [SourceCreate(url="https://a.example", retrieved_by="search")])
    raw = StrategyRecommendations.model_validate(strategy_for(["C1", "C1", "C1"]))
    first = raw.recommendations[0].model_copy(
        update={"next_steps": ["Talk to distributors (F2)", " (F3) "], "risks_tradeoffs": ["Thin margins (F10, F9)."]}
    )
    recs, _ = process_recommendations(raw.model_copy(update={"recommendations": [first]}), AnalysisOut(), evidence)
    assert recs[0].next_steps == ["Talk to distributors"]
    assert recs[0].risks_tradeoffs == ["Thin margins."]
