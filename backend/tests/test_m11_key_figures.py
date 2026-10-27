"""M11: key figures for charts (kept only when the number is in a verified claim it cites) and the
summary fields the home page shows (verified %, competitor count, time)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from schemas.api import ResearchRunSummary, report_highlights, verified_pct
from schemas.findings import AnalysisFindings, ClaimVerdict
from schemas.report import Report
from schemas.research import ResearchRun, SourceCreate
from tests.fakes import sample_findings
from workflow.claims import extract_claims, merge_verdicts
from workflow.report_assembler import Evidence, numbers_in, process_analysis

SOURCE = "https://www.notion.com"


def _evidence(verdicts: dict[str, str]) -> Evidence:
    """Sample claims with one rewritten to hold prices, and the verdicts given (default supported)."""
    sources = [SourceCreate(url=SOURCE, retrieved_by="search")]
    findings = sample_findings()
    company = findings.company
    pricing = company.description.model_copy(update={"text": "Plus costs $10 per member/month; Business $20."})
    findings = findings.model_copy(update={"company": company.model_copy(update={"pricing": pricing})})
    claims = extract_claims(findings, sources)
    answers = [
        ClaimVerdict(
            claim_id=c.id,
            verdict=verdicts.get(c.id, "supported"),
            confidence="high",
            reason="r",
            supporting_urls=[],
            source_year=None,
        )
        for c in claims
    ]
    return Evidence(merge_verdicts(claims, answers, sources), sources)


def _pricing_id(evidence: Evidence) -> str:
    return next(cid for cid, c in evidence.claims.items() if "$10" in c.text)


def _analysis(figures: list[dict[str, Any]]) -> AnalysisFindings:
    swot = {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}
    return AnalysisFindings.model_validate(
        {
            "comparison": [],
            "swot": swot,
            "trends": [],
            "opportunities": [],
            "risks": [],
            "data_gaps": [],
            "key_figures": figures,
        }
    )


def _figure(value: float, claim_ids: list[str], company: str = "Notion") -> dict[str, Any]:
    return {
        "label": " Entry paid plan price ",
        "company": company,
        "value": value,
        "unit": "USD per member per month",
        "year": None,
        "claim_ids": claim_ids,
    }


def test_numbers_in_text():
    assert numbers_in("$1,861.5 million, up 39% in 2025") == {1861.5, 39.0, 2025.0}
    assert numbers_in("no numbers") == set()


def test_a_figure_whose_number_is_in_its_verified_claim_is_kept():
    evidence = _evidence({})
    cid = _pricing_id(evidence)
    analysis, warnings = process_analysis(_analysis([_figure(10, [cid, "C999"])]), evidence)
    [figure] = analysis.key_figures
    assert (figure.label, figure.value, figure.claim_ids, figure.refs) == ("Entry paid plan price", 10, [cid], [1])
    assert not any("key figure" in w for w in warnings)


def test_figures_that_cannot_be_traced_are_dropped():
    evidence = _evidence({})
    cid = _pricing_id(evidence)
    other = next(c for c in evidence.claims if c != cid)
    analysis, warnings = process_analysis(
        _analysis(
            [
                _figure(12, [cid]),  # number not in the claim
                _figure(10, [other]),  # claim doesn't contain it
                _figure(10, ["C999"]),  # unknown claim
                _figure(10, []),  # no claim at all
            ]
        ),
        evidence,
    )
    assert analysis.key_figures == []
    assert sum("not in a verified claim" in w for w in warnings) == 4


def test_a_figure_on_an_unconfirmed_claim_is_dropped():
    evidence = _evidence({})
    cid = _pricing_id(evidence)
    evidence = _evidence({cid: "unsupported"})
    analysis, _ = process_analysis(_analysis([_figure(10, [cid])]), evidence)
    assert analysis.key_figures == []


def test_at_most_eight_figures():
    evidence = _evidence({})
    cid = _pricing_id(evidence)
    analysis, warnings = process_analysis(_analysis([_figure(10, [cid], f"Co{i}") for i in range(10)]), evidence)
    assert len(analysis.key_figures) == 8
    assert sum("more than 8" in w for w in warnings) == 2


def test_old_reports_without_key_figures_still_load():
    assert "key_figures" not in Report.model_json_schema().get("required", [])


# --- summary highlights ------------------------------------------------------------------------------


def _run(report: dict[str, Any] | None) -> ResearchRun:
    now = datetime(2026, 10, 26, tzinfo=UTC)
    return ResearchRun.model_validate(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "query": "Notion",
            "input_type": "name",
            "company_name": "Notion",
            "website_url": None,
            "status": "succeeded" if report else "running",
            "error": None,
            "current_step": None,
            "agno_run_id": None,
            "report": report,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "duration_ms": 59000 if report else None,
            "created_at": now,
            "finished_at": now if report else None,
            "updated_at": now,
        }
    )


def test_summary_shows_verified_share_competitors_and_time():
    report = {"validation": {"supported": 36, "claims_total": 44}, "competitor_landscape": [{}, {}, {}, {}, {}]}
    summary = ResearchRunSummary.of(_run(report))
    assert (summary.verified_pct, summary.competitor_count, summary.duration_ms) == (82, 5, 59000)


def test_summary_without_a_report():
    summary = ResearchRunSummary.of(_run(None))
    assert (summary.verified_pct, summary.competitor_count, summary.duration_ms) == (None, None, None)


def test_highlights_tolerate_odd_reports():
    assert report_highlights({"validation": {"supported": "x", "claims_total": 4}}) == {
        "verified_pct": None,
        "competitor_count": None,
    }
    assert report_highlights({"validation": {"supported": 0, "claims_total": 0}})["verified_pct"] is None
    assert verified_pct(1, 3) == 33
