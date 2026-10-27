"""Web research tools for the Researcher agent, built on Tavily's ASYNC client.

Why not Agno's built-in TavilyTools?
- It is synchronous: Agno calls sync tools directly on the event loop, so every search would
  freeze the whole API (including progress polling) for seconds.
- Its page extraction returns the full page (often 20–50k characters) to the LLM — expensive.
  We clean the page (no menus, images or link targets) and cap it.

These tools are async, cap page text, and always return the same JSON shape, which
`workflow/source_harvest.py` turns into numbered sources.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from agno.tools import Toolkit

from tools.page_text import clean_page_text

logger = logging.getLogger(__name__)

SEARCH_TOOL = "search_web"
READ_TOOL = "read_webpage"

MAX_RESULTS_CAP = 8
SEARCH_SNIPPET_CHARS = 1200
PAGE_TEXT_CHARS = 6000


class TavilyClientLike(Protocol):
    """The two methods of tavily.AsyncTavilyClient we use (tests pass a fake)."""

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]: ...

    async def extract(self, urls: list[str], **kwargs: Any) -> dict[str, Any]: ...


class WebResearchTools(Toolkit):
    def __init__(self, client: TavilyClientLike) -> None:
        self._client = client
        super().__init__(name="web_research", tools=[self.search_web, self.read_webpage])

    async def search_web(self, query: str, max_results: int = 5) -> str:
        """Search the web. Returns JSON: {"query", "results": [{"url", "title", "content"}]}.

        Use focused queries, e.g. "<company> pricing", "<company> competitors", "<company> funding 2026".

        Args:
            query: What to search for.
            max_results: Number of results (1-8). Defaults to 5.
        """
        max_results = max(1, min(int(max_results), MAX_RESULTS_CAP))
        try:
            response = await self._client.search(query=query, search_depth="basic", max_results=max_results)
        except Exception as exc:  # report to the model instead of crashing the run
            logger.warning("Tavily search failed for %r: %s", query, exc)
            return json.dumps({"query": query, "error": f"search failed: {type(exc).__name__}"})
        results = [
            {
                "url": item.get("url", ""),
                "title": item.get("title") or "",
                "content": (item.get("content") or "")[:SEARCH_SNIPPET_CHARS],
            }
            for item in response.get("results", [])
            if item.get("url")
        ]
        return json.dumps({"query": query, "results": results})

    async def read_webpage(self, url: str) -> str:
        """Read one web page. Returns JSON: {"url", "title", "content"} with the page text (shortened).

        Use it for the company's own website and for key pages found by search_web.

        Args:
            url: Full URL starting with http:// or https://.
        """
        if not url.startswith(("http://", "https://")):
            return json.dumps({"url": url, "error": "URL must start with http:// or https://"})
        try:
            response = await self._client.extract(urls=[url], extract_depth="basic")
        except Exception as exc:
            logger.warning("Tavily extract failed for %s: %s", url, exc)
            return json.dumps({"url": url, "error": f"read failed: {type(exc).__name__}"})
        results = response.get("results") or []
        if not results:
            return json.dumps({"url": url, "error": "page could not be read"})
        page = results[0]
        return json.dumps(
            {
                "url": page.get("url") or url,
                "title": page.get("title") or "",
                "content": clean_page_text(page.get("raw_content") or "")[:PAGE_TEXT_CHARS],
            }
        )
