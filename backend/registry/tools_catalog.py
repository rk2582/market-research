"""Tools by name, so agent specs can say tools=("web_research",) (same idea as the orchestrator's catalog)."""

from __future__ import annotations

from collections.abc import Callable

from agno.tools import Toolkit

from core.config import Settings
from tools.web_research import TavilyClientLike, WebResearchTools


class UnknownToolError(ValueError):
    pass


def tavily_client_for(settings: Settings) -> TavilyClientLike:
    from tavily import AsyncTavilyClient

    api_key = settings.tavily_api_key.get_secret_value() if settings.tavily_api_key else "missing-tavily-key"
    return AsyncTavilyClient(api_key=api_key)


def _web_research(settings: Settings, tavily_client: TavilyClientLike | None) -> Toolkit:
    return WebResearchTools(tavily_client or tavily_client_for(settings))


_TOOL_FACTORIES: dict[str, Callable[[Settings, TavilyClientLike | None], Toolkit]] = {
    "web_research": _web_research,
}

KNOWN_TOOLS = frozenset(_TOOL_FACTORIES)


def resolve_tools(
    names: tuple[str, ...], settings: Settings, *, tavily_client: TavilyClientLike | None = None
) -> list[Toolkit]:
    """Build the tools for an agent. `tavily_client` lets tests use a fake Tavily."""
    tools: list[Toolkit] = []
    for name in names:
        factory = _TOOL_FACTORIES.get(name)
        if factory is None:
            raise UnknownToolError(f"Unknown tool: {name!r}. Known tools: {sorted(KNOWN_TOOLS)}")
        tools.append(factory(settings, tavily_client))
    return tools
