"""The app as a whole: AgentOS wiring, routes, CORS, telemetry, lifespan."""

import os
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from main import AGENT_OS_ID, create_app
from tests.conftest import make_settings


def _paths(app: FastAPI) -> set[str]:
    return {route.path for route in app.routes}  # type: ignore[attr-defined]


def test_our_routes_and_agentos_routes_coexist(app: FastAPI):
    paths = _paths(app)
    assert "/api/v1/health" in paths
    for agentos_path in ("/health", "/config", "/workflows", "/agents", "/sessions", "/metrics"):
        assert agentos_path in paths, agentos_path


def test_app_metadata(app: FastAPI):
    assert app.title == "Delphi Market360"
    assert app.state.agent_os.id == AGENT_OS_ID


async def test_openapi_docs_available(client: httpx.AsyncClient):
    assert (await client.get("/docs")).status_code == 200
    spec = (await client.get("/openapi.json")).json()
    assert "/api/v1/health" in spec["paths"]
    assert "/workflows" in spec["paths"]


async def test_agentos_config_endpoint_works(client: httpx.AsyncClient):
    r = await client.get("/config")
    assert r.status_code == 200
    assert r.json()["os_id"] == AGENT_OS_ID


async def test_cors_allows_only_configured_frontend(client: httpx.AsyncClient):
    preflight = {"Access-Control-Request-Method": "GET"}
    ok = await client.options("/api/v1/health", headers={"Origin": "http://localhost:3001", **preflight})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3001"

    for origin in ("http://evil.example", "https://os.agno.com"):  # Agno's defaults must be replaced
        bad = await client.options("/api/v1/health", headers={"Origin": origin, **preflight})
        assert "access-control-allow-origin" not in bad.headers, origin


@pytest.fixture
def telemetry_calls(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Intercept Agno's launch telemetry so no test ever calls Agno's servers."""
    calls: list[object] = []
    monkeypatch.setattr("agno.api.os.log_os_telemetry", lambda **kwargs: calls.append(kwargs))
    return calls


def test_no_telemetry_sent_by_default(settings, telemetry_calls: list[object]):
    app = create_app(settings)
    assert app.state.agent_os.telemetry is False
    assert os.environ["AGNO_TELEMETRY"] == "false"
    assert telemetry_calls == []


def test_telemetry_can_be_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, telemetry_calls: list[object]):
    monkeypatch.setenv("AGNO_TELEMETRY", "false")  # monkeypatch restores the original value afterwards
    enabled = create_app(make_settings(tmp_path, agno_telemetry=True))
    assert enabled.state.agent_os.telemetry is True
    assert os.environ["AGNO_TELEMETRY"] == "true"
    assert len(telemetry_calls) == 1


def test_create_app_uses_get_settings_when_none_given(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from core.config import get_settings

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'env.db'}")
    get_settings.cache_clear()
    try:
        assert create_app().state.settings.database_url.endswith("env.db")
    finally:
        get_settings.cache_clear()


async def test_lifespan_creates_agno_tables_and_disposes_engine(app: FastAPI, tmp_path: Path):
    database = app.state.database
    async with app.router.lifespan_context(app):
        assert await database.ping() is True

    with sqlite3.connect(tmp_path / "test-agno.db") as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "agno_sessions" in tables  # created by AgentOS auto-provisioning
    assert database.engine.pool.checkedout() == 0


async def test_researcher_and_workflow_are_registered_in_agentos(client: httpx.AsyncClient):
    config = (await client.get("/config")).json()
    assert {a["id"] for a in config["agents"]} == {
        "identifier",
        "market_researcher",
        "market_analyst",
        "market_strategist",
        "researcher",
        "fact_checker",
        "analyst",
        "strategist",
        "report_writer",
    }
    assert {w["id"] for w in config["workflows"]} == {"market-research"}
    assert (await client.get("/workflows/market-research")).status_code == 200


def test_missing_keys_are_logged_at_startup(settings, caplog: pytest.LogCaptureFixture):
    create_app(settings)  # test settings have no keys
    assert "OPENAI_API_KEY is not set" in caplog.text
    assert "TAVILY_API_KEY is not set" in caplog.text


def test_no_key_warning_when_keys_present(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    create_app(make_settings(tmp_path, openai_api_key="sk-x", tavily_api_key="tvly-x"))
    assert "is not set" not in caplog.text
