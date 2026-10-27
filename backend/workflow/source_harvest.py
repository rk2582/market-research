"""Turns the Researcher's tool calls into numbered sources — the evidence behind every claim.

We take sources from what the tools actually returned (not from what the model says it read),
so a URL the model invents can never become a "source".
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from db.models.research import RetrievedBy
from schemas.research import SourceCreate
from tools.page_text import clean_page_text
from tools.web_research import PAGE_TEXT_CHARS, READ_TOOL, SEARCH_TOOL, TavilyClientLike

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Same page → same string: lower-case host, no fragment, no trailing slash on the path."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def url_key(url: str) -> str:
    """Matching key: like normalize_url, but http:// and https:// count as the same page."""
    normalized = normalize_url(url)
    return normalized.split("://", 1)[1] if "://" in normalized else normalized


_MD_LINK = re.compile(r"^\[(.+?)\]\(.*\)$", re.DOTALL)


def clean_title(title: Any) -> str | None:
    """Page titles sometimes arrive as markdown links: '[Name](/path "Name")' → 'Name'."""
    if not isinstance(title, str):
        return None
    title = title.strip()
    match = _MD_LINK.match(title)
    if match:
        title = match.group(1).strip()
    return title or None


def _parse(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return None
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def harvest_sources(tool_executions: list[Any] | None) -> list[SourceCreate]:
    """Sources in the order they were retrieved. A page that was read replaces its search snippet,
    because the full page text is better evidence."""
    by_url: dict[str, SourceCreate] = {}
    for execution in tool_executions or []:
        name = getattr(execution, "tool_name", None)
        if name not in (SEARCH_TOOL, READ_TOOL):
            continue
        data = _parse(getattr(execution, "result", None))
        if data is None or "error" in data:
            continue
        if name == SEARCH_TOOL:
            items = data.get("results") or []
            retrieved_by = RetrievedBy.SEARCH
        else:
            items = [data]
            retrieved_by = RetrievedBy.EXTRACT
        for item in items:
            url = item.get("url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                continue
            key = url_key(url)
            if key in by_url and retrieved_by == RetrievedBy.SEARCH:
                continue  # keep the first snippet, or the full page if already read
            stored_url = by_url[key].url if key in by_url else normalize_url(url)
            by_url[key] = SourceCreate(
                url=stored_url,
                title=clean_title(item.get("title")),
                excerpt=item.get("content") or None,
                retrieved_by=retrieved_by,
            )
    return list(by_url.values())


MAX_CITED_FETCH = 15  # one Tavily extract call (max 20 URLs); basic extract costs 1 credit per 5 pages


async def fetch_cited_pages(client: TavilyClientLike, urls: list[str]) -> list[SourceCreate]:
    """Read pages in one batched call (competitor homepages, pages cited but never retrieved) so the
    Fact-Checker can judge real text instead of marking claims unconfirmed. Failures are skipped."""
    wanted = list(dict.fromkeys(normalize_url(u) for u in urls if u.startswith(("http://", "https://"))))
    wanted = wanted[:MAX_CITED_FETCH]
    if not wanted:
        return []
    try:
        response = await client.extract(urls=wanted, extract_depth="basic")
    except Exception as exc:
        logger.warning("Fetching %d cited pages failed: %s", len(wanted), exc)
        return []
    pages: list[SourceCreate] = []
    for page in response.get("results") or []:
        url, text = page.get("url"), clean_page_text(page.get("raw_content") or "")
        if isinstance(url, str) and url.startswith(("http://", "https://")) and text.strip():
            pages.append(
                SourceCreate(
                    url=normalize_url(url),
                    title=clean_title(page.get("title")),
                    excerpt=text[:PAGE_TEXT_CHARS],
                    retrieved_by=RetrievedBy.EXTRACT,
                )
            )
    return pages
