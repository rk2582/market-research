"""Delphi Market360 backend entry point.

Run:  uv run uvicorn main:create_app --factory --reload --port 8000

One app, two kinds of routes:
- Our product routes under /api/v1 (registered on `base_app`).
- AgentOS built-in routes (/workflows, /agents, /sessions, /metrics, /config, /health, ...).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from agno.os import AgentOS
from fastapi import FastAPI

from api.health import router as health_router
from api.research import router as research_router
from core.agno_db import build_agno_db
from core.config import Settings, get_settings
from core.errors import register_exception_handlers
from core.logging import setup_logging
from db.session import Database
from registry.factory import build_all_agents
from services.identify_service import IdentifyService
from services.research_service import ResearchService
from tools.web_research import TavilyClientLike
from workflow.research_workflow import build_research_workflow

AGENT_OS_ID = "delphi-market360"
logger = logging.getLogger(__name__)


def _warn_about_missing_keys(settings: Settings) -> None:
    """The API still starts without keys (useful for tests and UI work); research runs will fail."""
    for name, value in (("OPENAI_API_KEY", settings.openai_api_key), ("TAVILY_API_KEY", settings.tavily_api_key)):
        if value is None:
            logger.warning("%s is not set in backend/.env — research runs will fail until it is.", name)


def create_app(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
    tavily_client: TavilyClientLike | None = None,
) -> FastAPI:
    """Build the app. `http_client` / `tavily_client` replace OpenAI / Tavily in tests."""
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    # Agno reads this for every agent/team/workflow it creates.
    os.environ["AGNO_TELEMETRY"] = "true" if settings.agno_telemetry else "false"

    database = Database(settings.database_url)
    agno_db = build_agno_db(settings)
    _warn_about_missing_keys(settings)

    # The workflow reports step progress to the service; the service starts the workflow.
    async def progress(research_id: str, step: str) -> None:
        await research_service.progress(research_id, step)

    workflow = build_research_workflow(
        settings, agno_db, http_client=http_client, tavily_client=tavily_client, progress=progress
    )
    research_service = ResearchService(database, workflow, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:  # runs left "running" by a previous process: save the finished ones, fail the rest
            await research_service.reconcile_after_restart()
        except Exception:
            logger.exception("Startup reconcile failed (is the database migrated? run: uv run alembic upgrade head)")
        yield
        await database.dispose()

    base_app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI market research and competitive intelligence (local POC).",
        lifespan=lifespan,
    )
    base_app.state.settings = settings
    base_app.state.database = database
    base_app.state.research_service = research_service
    base_app.state.identify_service = IdentifyService(settings, http_client=http_client, tavily_client=tavily_client)
    register_exception_handlers(base_app)
    base_app.include_router(health_router)
    base_app.include_router(research_router)

    agent_os = AgentOS(
        id=AGENT_OS_ID,
        name=settings.app_name,
        description="Market research workflow and agents",
        db=agno_db,
        agents=build_all_agents(settings),  # so each agent can be tried alone from /docs
        workflows=[workflow],  # the same instance our API starts runs on
        base_app=base_app,
        on_route_conflict="error",  # fail fast if our routes ever clash with AgentOS routes
        cors_allowed_origins=settings.cors_origins,  # replaces Agno's default origin list
        telemetry=settings.agno_telemetry,
        tracing=settings.tracing_enabled,
    )
    app = agent_os.get_app()
    app.state.agent_os = agent_os
    return app
