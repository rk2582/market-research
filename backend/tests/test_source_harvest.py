import json
from types import SimpleNamespace

import pytest

from tests.fakes import FakeTavily, sample_findings
from workflow.claims import dedupe_findings
from workflow.source_harvest import MAX_CITED_FETCH, fetch_cited_pages, harvest_sources, normalize_url


def _exec(tool: str, result: object) -> SimpleNamespace:
    return SimpleNamespace(tool_name=tool, result=result if isinstance(result, str) else json.dumps(result))


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("https://WWW.Notion.com/", "https://www.notion.com"),
        ("https://notion.com/pricing/#plans", "https://notion.com/pricing"),
        ("HTTPS://a.example/x?y=1", "https://a.example/x?y=1"),
        ("  https://a.example/a/  ", "https://a.example/a"),
    ],
)
def test_normalize_url(raw: str, normalized: str):
    assert normalize_url(raw) == normalized


def test_search_results_become_sources_in_order():
    sources = harvest_sources(
        [
            _exec("search_web", {"results": [{"url": "https://a.example", "title": "A", "content": "ca"}]}),
            _exec("search_web", {"results": [{"url": "https://b.example", "title": "", "content": ""}]}),
        ]
    )
    assert [(s.url, s.title, s.excerpt, s.retrieved_by) for s in sources] == [
        ("https://a.example", "A", "ca", "search"),
        ("https://b.example", None, None, "search"),
    ]


def test_read_page_replaces_search_snippet_but_keeps_position():
    sources = harvest_sources(
        [
            _exec("search_web", {"results": [{"url": "https://a.example/", "content": "snippet"}]}),
            _exec("search_web", {"results": [{"url": "https://b.example", "content": "b"}]}),
            _exec("read_webpage", {"url": "https://a.example", "title": "Full", "content": "full page"}),
            _exec("search_web", {"results": [{"url": "https://a.example", "content": "later snippet"}]}),
        ]
    )
    assert [(s.url, s.excerpt, s.retrieved_by) for s in sources] == [
        ("https://a.example", "full page", "extract"),
        ("https://b.example", "b", "search"),
    ]


def test_ignores_errors_bad_json_other_tools_and_bad_urls():
    sources = harvest_sources(
        [
            _exec("search_web", {"query": "q", "error": "search failed"}),
            _exec("read_webpage", "not json at all"),
            _exec("read_webpage", "[1, 2]"),  # JSON but not an object
            SimpleNamespace(tool_name="read_webpage", result=None),
            _exec("some_other_tool", {"url": "https://x.example"}),
            _exec("search_web", {"results": [{"url": "ftp://x.example"}, {"url": None}, {"title": "no url"}]}),
            SimpleNamespace(tool_name="search_web", result={"results": [{"url": "https://dict.example"}]}),
        ]
    )
    assert [s.url for s in sources] == ["https://dict.example"]


def test_no_tools_means_no_sources():
    assert harvest_sources(None) == []
    assert harvest_sources([]) == []


async def test_fetch_cited_pages_batches_filters_and_caps():
    urls = ["ftp://x.example", "https://a.example/", "https://a.example"] + [f"https://p{i}.example" for i in range(20)]
    tavily = FakeTavily(pages={"https://a.example": "Page A", "https://p0.example": "   "})
    pages = await fetch_cited_pages(tavily, urls)
    assert len(tavily.calls) == 1 and len(tavily.calls[0][1]) == MAX_CITED_FETCH  # one call, capped, deduped
    assert [p.url for p in pages] == ["https://a.example"]  # empty page text is skipped
    assert pages[0].retrieved_by == "extract"


async def test_fetch_cited_pages_survives_tavily_failure():
    assert await fetch_cited_pages(FakeTavily(fail=True), ["https://a.example"]) == []
    assert await fetch_cited_pages(FakeTavily(), []) == []


def test_dedupe_findings_removes_repeated_competitors_and_statements():
    findings = sample_findings()
    company = findings.company
    doubled = findings.model_copy(
        update={
            "company": company.model_copy(update={"products_services": company.products_services * 2}),
            "competitors": findings.competitors * 2,
            "industry_context": findings.industry_context * 3,
        }
    )
    clean = dedupe_findings(doubled)
    assert len(clean.competitors) == len(findings.competitors)
    assert clean.company.products_services == company.products_services
    assert clean.industry_context == findings.industry_context
