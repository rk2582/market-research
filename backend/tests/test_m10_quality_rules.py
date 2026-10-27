"""M10 quality rules, from the Facebook/Meta live report:
- the company's own brands are not competitors (Instagram for Meta);
- each competitor claim also gets the competitor's homepage as evidence, credited only if it supports the claim;
- competitor columns with no sourced data are dropped from the comparison table;
- opportunities and risks are never labelled 'fact'; verdict words are removed from cells.
"""

from __future__ import annotations

from typing import Any

from schemas.findings import AnalysisFindings, ClaimVerdict, ResearchFindings
from schemas.research import SourceCreate
from tests.conftest import make_settings
from tests.fakes import FakeOpenAI, FakeTavily, prompt_payload, sample_findings, tool_call
from workflow.claims import (
    add_competitor_homepages,
    competitor_homepages_to_fetch,
    drop_own_brands,
    extract_claims,
    merge_verdicts,
)
from workflow.report_assembler import Evidence, process_analysis

SOURCE = "https://www.notion.com"


def _with_competitor(findings: ResearchFindings, **changes: Any) -> ResearchFindings:
    comp = findings.competitors[0]
    for field in ("description",):
        if field in changes and isinstance(changes[field], str):
            changes[field] = comp.description.model_copy(update={"text": changes[field]})
    return findings.model_copy(update={"competitors": [comp.model_copy(update=changes), findings.competitors[1]]})


# --- own brands ------------------------------------------------------------------------------------


def test_real_competitors_are_kept():
    findings, notes = drop_own_brands(sample_findings())
    assert [c.name for c in findings.competitors] == ["Coda", "Confluence"] and notes == []


def test_same_name_or_same_website_is_dropped():
    same_name = _with_competitor(sample_findings(), name="notion")
    same_site = _with_competitor(sample_findings(), website="https://notion.com")
    assert [c.name for c in drop_own_brands(same_name)[0].competitors] == ["Confluence"]
    findings, notes = drop_own_brands(same_site)
    assert [c.name for c in findings.competitors] == ["Confluence"]
    assert notes == ["Removed competitor Coda: it has the same website as the company."]


def test_a_brand_the_company_owns_is_dropped():
    findings = sample_findings()
    meta = findings.company.model_copy(update={"name": "Meta Platforms, Inc. (formerly Facebook, Inc.)"})
    findings = _with_competitor(
        findings.model_copy(update={"company": meta}),
        name="Instagram",
        website="https://instagram.com",
        description="Instagram is a photo app owned by Meta that competes with Facebook.",
    )
    kept, notes = drop_own_brands(findings)
    assert [c.name for c in kept.competitors] == ["Confluence"]
    assert notes == ["Removed competitor Instagram: its description says the company owns it."]


def test_a_competitor_listed_as_the_company_product_is_dropped():
    findings = sample_findings()
    products = [findings.company.products_services[0].model_copy(update={"text": "WhatsApp messenger for chat."})]
    company = findings.company.model_copy(update={"products_services": products})
    findings = _with_competitor(findings.model_copy(update={"company": company}), name="WhatsApp")
    _, notes = drop_own_brands(findings)
    assert notes == ["Removed competitor WhatsApp: it is listed as one of the company's own products."]


def test_mentioning_a_competitor_inside_a_product_line_is_fine():
    findings = sample_findings()
    products = [findings.company.products_services[0].model_copy(update={"text": "Import from Coda and Confluence."})]
    company = findings.company.model_copy(update={"products_services": products})
    kept, _ = drop_own_brands(findings.model_copy(update={"company": company}))
    assert len(kept.competitors) == 2


# --- competitor homepages ----------------------------------------------------------------------------


def test_homepages_to_fetch_skips_those_already_read():
    sources = [SourceCreate(url="https://www.coda.io", retrieved_by="extract")]  # www. doesn't matter
    assert competitor_homepages_to_fetch(sample_findings(), sources) == ["https://confluence.com"]
    deep_page = [SourceCreate(url="https://coda.io/pricing", retrieved_by="extract")]  # not the homepage
    assert competitor_homepages_to_fetch(sample_findings(), deep_page) == ["https://coda.io", "https://confluence.com"]


def _claims_with_homepage() -> tuple[list, list[SourceCreate]]:
    sources = [
        SourceCreate(url=SOURCE, retrieved_by="search"),
        SourceCreate(url="https://coda.io", retrieved_by="extract", excerpt="Coda is an all-in-one doc."),
    ]
    findings = sample_findings()
    return add_competitor_homepages(extract_claims(findings, sources), findings, sources), sources


def test_competitor_claims_get_their_homepage_as_extra_evidence():
    claims, _ = _claims_with_homepage()
    coda = [c for c in claims if c.subject == "Coda"]
    assert coda and all(c.source_urls == [SOURCE, "https://coda.io"] for c in coda)
    assert all(c.code_added_urls == ["https://coda.io"] for c in coda)
    others = [c for c in claims if c.subject != "Coda"]
    assert all("https://coda.io" not in c.source_urls and c.code_added_urls == [] for c in others)


def _verdict(cid: str, verdict: str, supporting: list[str]) -> ClaimVerdict:
    return ClaimVerdict(
        claim_id=cid, verdict=verdict, confidence="high", reason="r", supporting_urls=supporting, source_year=None
    )


def test_only_sources_the_fact_checker_names_are_credited():
    claims, sources = _claims_with_homepage()
    a, b, c = [c for c in claims if c.subject == "Coda"]
    d = claims[0]  # a company claim
    checked = merge_verdicts(
        [a, b, c, d],
        [
            _verdict(a.id, "supported", ["https://coda.io/"]),  # homepage holds the evidence
            _verdict(b.id, "supported", []),  # no list given: keep the Researcher's source only
            _verdict(c.id, "unsupported", ["https://coda.io"]),  # not supported: added page never credited
            _verdict(d.id, "partially_supported", ["https://unknown.example"]),  # unknown URL ignored
        ],
        sources,
    )
    assert [x.source_urls for x in checked] == [["https://coda.io"], [SOURCE], [SOURCE], [SOURCE]]


# --- analysis -----------------------------------------------------------------------------------------


def _analysis(cells_for_snapchat: dict[str, Any]) -> AnalysisFindings:
    def insight(text: str, kind: str = "fact") -> dict[str, Any]:
        return {"text": text, "kind": kind, "evidence_claim_ids": ["C1"]}

    def row(dimension: str) -> dict[str, Any]:
        return {
            "dimension": dimension,
            "cells": [
                {"company": "Meta", "value": "Social apps.", "claim_ids": ["C1"]},
                {"company": "TikTok", "value": "Short video. Unsupported.", "claim_ids": ["C1"]},
                {"company": "Snapchat", **cells_for_snapchat},
            ],
        }

    return AnalysisFindings.model_validate(
        {
            "comparison": [row("Core offering"), row("Positioning")],
            "swot": {
                "strengths": [insight("Big audience.")],
                "weaknesses": [],
                "opportunities": [insight("Grow AI tools.")],
                "threats": [insight("Strong rivals.")],
            },
            "trends": [insight("Video grows.")],
            "opportunities": [insight("Expand verification.")],
            "risks": [insight("Ad dependence.")],
            "data_gaps": [],
            "key_figures": [],
        }
    )


def _evidence() -> Evidence:
    sources = [SourceCreate(url=SOURCE, retrieved_by="search")]
    checked = merge_verdicts(
        extract_claims(sample_findings(), sources)[:1], [_verdict("C1", "supported", [SOURCE])], sources
    )
    return Evidence(checked, sources)


def test_competitor_with_no_sourced_cells_is_dropped_from_the_table():
    analysis, warnings = process_analysis(_analysis({"value": "Not publicly available", "claim_ids": []}), _evidence())
    assert [[c.company for c in row.cells] for row in analysis.comparison] == [["Meta", "TikTok"]] * 2
    assert "Dropped Snapchat from the comparison table: no sourced data." in warnings
    assert analysis.comparison[0].cells[1].value == "Short video."  # verdict word removed


def test_competitor_with_some_sourced_data_stays():
    analysis, _ = process_analysis(_analysis({"value": "Stories.", "claim_ids": ["C1"]}), _evidence())
    assert [c.company for c in analysis.comparison[0].cells] == ["Meta", "TikTok", "Snapchat"]


def test_opportunities_and_risks_are_never_facts():
    analysis, _ = process_analysis(_analysis({"value": "x", "claim_ids": []}), _evidence())
    assert analysis.swot.strengths[0].kind == "fact" and analysis.swot.threats[0].kind == "fact"
    assert analysis.trends[0].kind == "fact"
    assert analysis.swot.opportunities[0].kind == "interpretation"
    assert analysis.opportunities[0].kind == "interpretation"
    assert analysis.risks[0].kind == "interpretation"


# --- end to end through the workflow ----------------------------------------------------------------


async def test_workflow_fetches_competitor_homepages_and_credits_them(tmp_path):
    from core.agno_db import build_agno_db
    from tests.fakes import analysis_for, narrative_for, strategy_for, validation_for
    from workflow.research_workflow import build_research_workflow, outcome_from_run

    tavily = FakeTavily(search_results={"Notion": [{"url": SOURCE + "/", "title": "Notion", "content": "Workspace"}]})
    tavily.pages["https://coda.io"] = "Coda is an all-in-one doc for teams."

    def checker(body: dict[str, Any]) -> dict[str, Any]:
        claims = prompt_payload(body)["claims"]
        answer = validation_for([c["id"] for c in claims])
        for verdict, claim in zip(answer["verdicts"], claims, strict=True):
            verdict["supporting_urls"] = ["https://coda.io"] if "https://coda.io" in claim["sources"] else []
        return answer

    ids = [c.id for c in extract_claims(sample_findings(), [SourceCreate(url=SOURCE, retrieved_by="search")])]
    openai = FakeOpenAI(
        {
            "ResearchFindings": [[tool_call("search_web", query="Notion")], sample_findings()],
            "ValidationResult": [checker],
            "AnalysisFindings": [analysis_for("Notion", "Coda", ids)],
            "StrategyRecommendations": [strategy_for(["F1", "F2", "F5"])],
            "ReportNarrative": [narrative_for("C2")],
        }
    )
    settings = make_settings(tmp_path, openai_api_key="sk-test", tavily_api_key="tvly-test")
    workflow = build_research_workflow(
        settings, build_agno_db(settings), http_client=openai.client, tavily_client=tavily
    )
    result = outcome_from_run(await workflow.arun(input="Notion", session_id="s1", additional_data={}))

    assert ("extract", ["https://coda.io", "https://confluence.com"]) in tavily.calls  # one batched call
    report = result.report
    refs = {r.url: r.ref for r in report.references}
    assert "https://coda.io" in refs
    coda = next(c for c in report.competitor_landscape if c.name == "Coda")
    assert all(claim.refs == [refs["https://coda.io"]] for g in coda.facts for claim in g.claims)
    confluence = next(c for c in report.competitor_landscape if c.name == "Confluence")
    assert all(claim.refs == [refs[SOURCE]] for g in confluence.facts for claim in g.claims)
