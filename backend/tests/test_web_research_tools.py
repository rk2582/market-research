import json
from pathlib import Path

import pytest
from agno.models.openai import OpenAIChat

from registry.models import OPENAI_MAX_RETRIES, build_model
from registry.tools_catalog import UnknownToolError, resolve_tools
from tests.conftest import make_settings
from tests.fakes import FakeTavily
from tools.web_research import MAX_RESULTS_CAP, PAGE_TEXT_CHARS, SEARCH_SNIPPET_CHARS, WebResearchTools


async def test_search_returns_compact_json_and_caps_snippets():
    tavily = FakeTavily(
        search_results={
            "q": [
                {"url": "https://a.example", "title": "A", "content": "x" * 5000, "score": 1},
                {"title": "no url — dropped", "content": "y"},
            ]
        }
    )
    data = json.loads(await WebResearchTools(tavily).search_web("q"))
    assert data["query"] == "q"
    assert data["results"] == [{"url": "https://a.example", "title": "A", "content": "x" * SEARCH_SNIPPET_CHARS}]


@pytest.mark.parametrize(("asked", "sent"), [(0, 1), (3, 3), (50, MAX_RESULTS_CAP)])
async def test_search_clamps_max_results(asked: int, sent: int):
    captured = {}

    class Recorder(FakeTavily):
        async def search(self, query, **kwargs):
            captured.update(kwargs)
            return {"results": []}

    await WebResearchTools(Recorder()).search_web("q", max_results=asked)
    assert captured == {"search_depth": "basic", "max_results": sent}


async def test_read_webpage_caps_page_text():
    tavily = FakeTavily(pages={"https://a.example": "p" * 20_000})
    data = json.loads(await WebResearchTools(tavily).read_webpage("https://a.example"))
    assert data["url"] == "https://a.example"
    assert len(data["content"]) == PAGE_TEXT_CHARS


async def test_read_webpage_rejects_non_http_urls_without_calling_tavily():
    tavily = FakeTavily()
    data = json.loads(await WebResearchTools(tavily).read_webpage("file:///etc/passwd"))
    assert "error" in data
    assert tavily.calls == []


async def test_read_webpage_reports_unreadable_page():
    data = json.loads(await WebResearchTools(FakeTavily()).read_webpage("https://missing.example"))
    assert data == {"url": "https://missing.example", "error": "page could not be read"}


async def test_tavily_failures_are_reported_to_the_model_not_raised():
    tools = WebResearchTools(FakeTavily(fail=True))
    assert "search failed" in json.loads(await tools.search_web("q"))["error"]
    assert "read failed" in json.loads(await tools.read_webpage("https://a.example"))["error"]


def test_toolkit_exposes_two_async_tools():
    toolkit = WebResearchTools(FakeTavily())
    assert set(toolkit.async_functions or toolkit.functions) >= {"search_web", "read_webpage"}


def test_resolve_tools(tmp_path: Path):
    settings = make_settings(tmp_path, tavily_api_key="tvly-x")
    [toolkit] = resolve_tools(("web_research",), settings)  # builds the real async Tavily client
    assert isinstance(toolkit, WebResearchTools)
    assert resolve_tools((), settings) == []
    with pytest.raises(UnknownToolError, match="nope"):
        resolve_tools(("nope",), settings)


def test_resolve_tools_without_key_still_builds(tmp_path: Path):
    [toolkit] = resolve_tools(("web_research",), make_settings(tmp_path))
    assert isinstance(toolkit, WebResearchTools)


def test_build_model_uses_per_agent_model_and_key(tmp_path: Path):
    settings = make_settings(tmp_path, openai_api_key="sk-x", default_model="gpt-default", model_analyst="gpt-big")
    analyst = build_model(settings, "analyst")
    assert isinstance(analyst, OpenAIChat)
    assert (analyst.id, analyst.api_key, analyst.max_retries) == ("gpt-big", "sk-x", OPENAI_MAX_RETRIES)
    assert build_model(settings, "researcher").id == "gpt-default"
    assert build_model(make_settings(tmp_path), "researcher").api_key is None
