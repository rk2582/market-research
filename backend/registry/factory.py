"""Builds Agno agents from AgentSpecs (one place, like the orchestrator's factory)."""

from __future__ import annotations

import httpx
from agno.agent import Agent

from agents.analyst import ANALYST
from agents.fact_checker import FACT_CHECKER
from agents.identifier import IDENTIFIER
from agents.market import MARKET_ANALYST, MARKET_RESEARCHER, MARKET_STRATEGIST
from agents.report_writer import REPORT_WRITER
from agents.researcher import RESEARCHER
from agents.spec import AgentSpec
from agents.strategist import STRATEGIST
from core.config import Settings
from registry.models import build_model
from registry.tools_catalog import resolve_tools
from tools.web_research import TavilyClientLike

# The five workflow agents, in order; the Identifier runs before the workflow (confirm step).
WORKFLOW_SPECS: tuple[AgentSpec, ...] = (RESEARCHER, FACT_CHECKER, ANALYST, STRATEGIST, REPORT_WRITER)
# Market-entry mode (M13) swaps in these three; the Fact-Checker and Report Writer are shared.
MARKET_SPECS: tuple[AgentSpec, ...] = (
    MARKET_RESEARCHER,
    FACT_CHECKER,
    MARKET_ANALYST,
    MARKET_STRATEGIST,
    REPORT_WRITER,
)
ALL_SPECS: tuple[AgentSpec, ...] = (IDENTIFIER, *WORKFLOW_SPECS, MARKET_RESEARCHER, MARKET_ANALYST, MARKET_STRATEGIST)


def build_agent(
    spec: AgentSpec,
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
    tavily_client: TavilyClientLike | None = None,
) -> Agent:
    """A fresh agent for one run. Test hooks: `http_client` (fake OpenAI), `tavily_client` (fake Tavily)."""
    return Agent(
        id=spec.key,
        name=spec.name,
        role=spec.role,
        description=f"{spec.role} ({spec.version})",
        model=build_model(settings, spec.key, http_client=http_client),
        tools=resolve_tools(spec.tools, settings, tavily_client=tavily_client),
        tool_call_limit=spec.tool_call_limit,
        instructions=list(spec.instructions),
        output_schema=spec.output_schema,
        add_datetime_to_context=True,  # "last 12 months" needs today's date
        markdown=False,
        retries=0,  # the OpenAI client already retries transient errors
        telemetry=settings.agno_telemetry,
        metadata={"version": spec.version},
    )


def build_all_agents(settings: Settings) -> list[Agent]:
    return [build_agent(spec, settings) for spec in ALL_SPECS]
