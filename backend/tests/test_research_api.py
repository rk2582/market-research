"""Contract tests for /api/v1/research: 202 / 200 / 404 / 409 / 422 / 429, progress, saving
results, and reconciling after a restart.

The whole app runs (AgentOS + our routes + the real workflow on Agno); only OpenAI and Tavily are fakes.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import update

from db.base import Base
from db.models.research import InputType, ResearchRunRow, RunStatus
from main import create_app
from repositories.research_repo import ResearchRunRepository
from repositories.source_repo import SourceRepository
from schemas.report import Report
from schemas.research import ResearchRunCreate
from services.research_service import RESTART_ERROR, build_steps
from tests.conftest import make_settings
from tests.fakes import FakeOpenAI, FakeTavily
from tests.test_research_workflow import happy_script, notion_tavily

API = "/api/v1/research"
TERMINAL = {"succeeded", "partial", "failed"}


@asynccontextmanager
async def api(
    tmp_path: Path, openai: FakeOpenAI | None = None, tavily: FakeTavily | None = None, **overrides: object
) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    settings = make_settings(tmp_path, openai_api_key="sk-test", tavily_api_key="tvly-test", **overrides)
    openai = openai or FakeOpenAI(happy_script())
    app = create_app(settings, http_client=openai.client, tavily_client=tavily or notion_tavily())
    async with app.state.database.engine.begin() as conn:  # product tables (tests don't run Alembic)
        await conn.run_sync(Base.metadata.create_all)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    await app.state.database.dispose()


async def wait_until_finished(client: httpx.AsyncClient, run_id: str) -> dict:
    for _ in range(300):
        body = (await client.get(f"{API}/{run_id}")).json()
        if body["status"] in TERMINAL:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("run did not finish")


async def insert_run(app: FastAPI, *, status: RunStatus = RunStatus.RUNNING, **values: object) -> uuid.UUID:
    async with app.state.database.session() as session:
        repo = ResearchRunRepository(session)
        run = await repo.create(ResearchRunCreate(query="Notion", input_type=InputType.NAME))
        if status != RunStatus.RUNNING:
            await repo.finish(run.id, status=status, error=values.pop("error", None))
        if values:
            await session.execute(update(ResearchRunRow).where(ResearchRunRow.id == run.id).values(**values))
    return run.id


# --- happy path ---------------------------------------------------------------------------------


async def test_start_poll_and_fetch_report(tmp_path: Path):
    async with api(tmp_path) as (client, app):
        started = time.perf_counter()
        response = await client.post(API, json={"query": "  Notion "})
        assert time.perf_counter() - started < 0.5  # the workflow runs in the background
        assert response.status_code == 202
        summary = response.json()
        assert summary["status"] == "running" and summary["input_type"] == "name" and summary["query"] == "Notion"

        detail = await wait_until_finished(client, summary["id"])
        assert detail["status"] == "succeeded" and detail["has_report"] is True
        assert detail["current_step"] is None and detail["error"] is None
        assert detail["company_name"] == "Notion" and detail["finished_at"]
        assert detail["created_at"].endswith("Z") and detail["finished_at"].endswith("Z")  # explicit UTC
        assert [(s["name"], s["status"]) for s in detail["steps"]] == [
            (n, "completed") for n in ("research", "validate", "analyse", "strategise", "write")
        ]
        assert detail["totals"]["total_tokens"] > 0 and detail["totals"]["duration_ms"] >= 0

        report_response = await client.get(f"{API}/{summary['id']}/report")
        assert report_response.status_code == 200
        report = Report.model_validate(report_response.json())
        assert report.meta.outcome == "succeeded" and report.references

        # Sources saved with the same numbers as the report, and the excerpt that was fact-checked
        async with app.state.database.session() as session:
            sources = await SourceRepository(session).list_for_run(uuid.UUID(summary["id"]))
        assert [(s.ref_number, s.url) for s in sources] == [(r.ref, r.url) for r in report.references]
        assert all(s.excerpt for s in sources)

        listing = (await client.get(API)).json()
        assert listing["total"] == 1 and listing["items"][0]["status"] == "succeeded"


async def test_url_query_is_passed_to_the_researcher(tmp_path: Path):
    openai = FakeOpenAI(happy_script())
    async with api(tmp_path, openai) as (client, _):
        summary = (await client.post(API, json={"query": "Notion.so/product"})).json()
        assert summary["input_type"] == "url"
        detail = await wait_until_finished(client, summary["id"])
        assert detail["website_url"] == "https://notion.so/product"
    prompt = str(openai.requests_for("ResearchFindings")[0]["messages"][-1]["content"])
    assert "https://notion.so/product" in prompt


async def test_progress_writes_current_step_only_while_running(tmp_path: Path):
    async with api(tmp_path) as (_, app):
        service = app.state.research_service
        running = await insert_run(app)
        done = await insert_run(app, status=RunStatus.SUCCEEDED)
        await service.progress(str(running), "analyse")
        await service.progress(str(done), "analyse")
        async with app.state.database.session() as session:
            repo = ResearchRunRepository(session)
            assert (await repo.get(running)).current_step == "analyse"
            assert (await repo.get(done)).current_step is None


def test_steps_while_running_come_from_current_step():
    steps = build_steps("analyse", None, finished=False)
    assert [s.status for s in steps] == ["completed", "completed", "running", "pending", "pending"]
    assert [s.status for s in build_steps(None, None, finished=False)] == ["pending"] * 5
    assert [s.status for s in build_steps(None, None, finished=True)] == ["skipped"] * 5


# --- failures and partial reports -----------------------------------------------------------------


async def test_research_failure_gives_a_failed_run_without_report(tmp_path: Path):
    openai = FakeOpenAI(happy_script(ResearchFindings=[400]))
    async with api(tmp_path, openai) as (client, _):
        run_id = (await client.post(API, json={"query": "Notion"})).json()["id"]
        detail = await wait_until_finished(client, run_id)
        assert detail["status"] == "failed" and detail["has_report"] is False
        assert detail["error"].startswith("research step failed")
        assert [s["status"] for s in detail["steps"]] == ["failed", "skipped", "skipped", "skipped", "skipped"]
        response = await client.get(f"{API}/{run_id}/report")
        assert response.status_code == 409 and response.json()["code"] == "report_not_ready"
        assert "research step failed" in response.json()["detail"]


async def test_analyst_failure_gives_a_partial_run_with_report(tmp_path: Path):
    openai = FakeOpenAI(happy_script(AnalysisFindings=["not valid JSON"]))
    async with api(tmp_path, openai) as (client, _):
        run_id = (await client.post(API, json={"query": "Notion"})).json()["id"]
        detail = await wait_until_finished(client, run_id)
        assert detail["status"] == "partial" and detail["has_report"] is True
        report = (await client.get(f"{API}/{run_id}/report")).json()
        assert "swot" in report["meta"]["missing_sections"]


async def test_workflow_that_cannot_start_returns_500_and_fails_the_run(tmp_path: Path, monkeypatch):
    async with api(tmp_path) as (client, app):

        async def broken_arun(**kwargs):
            raise RuntimeError("database locked")

        monkeypatch.setattr(app.state.research_service.workflow, "arun", broken_arun)
        response = await client.post(API, json={"query": "Notion"})
        assert response.status_code == 500 and response.json()["code"] == "start_failed"
        assert "database locked" not in response.text  # no internals leaked
        item = (await client.get(API)).json()["items"][0]
        assert item["status"] == "failed"


# --- validation, not found, conflict, capacity ---------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [{}, {"query": ""}, {"query": "x" * 301}, {"query": "http://localhost:3000"}, {"query": "http://10.1.2.3"}],
)
async def test_invalid_input_is_422(tmp_path: Path, body: dict):
    async with api(tmp_path) as (client, _):
        response = await client.post(API, json=body)
        assert response.status_code == 422
        assert (await client.get(API)).json()["total"] == 0  # nothing was created


async def test_unknown_run_is_404_and_bad_id_is_422(tmp_path: Path):
    async with api(tmp_path) as (client, _):
        missing = uuid.uuid4()
        for path in (f"{API}/{missing}", f"{API}/{missing}/report"):
            response = await client.get(path)
            assert response.status_code == 404 and response.json()["code"] == "run_not_found"
        assert (await client.get(f"{API}/not-a-uuid")).status_code == 422
        assert (await client.get(API, params={"limit": 0})).status_code == 422
        assert (await client.get(API, params={"limit": 101})).status_code == 422


async def test_report_of_a_running_run_is_409(tmp_path: Path):
    async with api(tmp_path) as (client, app):
        run_id = await insert_run(app)
        response = await client.get(f"{API}/{run_id}/report")
        assert response.status_code == 409 and response.json()["code"] == "report_not_ready"
        assert "still running" in response.json()["detail"]


async def test_capacity_limit_is_429(tmp_path: Path):
    async with api(tmp_path, max_concurrent_runs=1) as (client, app):
        await insert_run(app)  # one run already in progress
        response = await client.post(API, json={"query": "Monzo"})
        assert response.status_code == 429 and response.json()["code"] == "capacity_reached"
        assert (await client.get(API)).json()["total"] == 1


async def test_simultaneous_starts_respect_the_limit(tmp_path: Path):
    async with api(tmp_path, max_concurrent_runs=1) as (client, _):
        responses = await asyncio.gather(*(client.post(API, json={"query": q}) for q in ("Notion", "Monzo")))
        assert sorted(r.status_code for r in responses) == [202, 429]


async def test_finished_runs_free_capacity_without_being_polled(tmp_path: Path):
    async with api(tmp_path, max_concurrent_runs=1) as (client, app):
        first = (await client.post(API, json={"query": "Notion"})).json()
        workflow = app.state.research_service.workflow
        async with app.state.database.session() as session:
            agno_run_id = (await ResearchRunRepository(session).get(uuid.UUID(first["id"]))).agno_run_id
        for _ in range(300):  # wait on Agno directly: nobody polls our API
            run = await workflow.aget_run(agno_run_id, session_id=first["id"])
            if run is not None and str(getattr(run.status, "value", run.status)) == "COMPLETED":
                break
            await asyncio.sleep(0.05)
        response = await client.post(API, json={"query": "Monzo"})
        assert response.status_code == 202  # the finished run was saved before counting


# --- reconciling --------------------------------------------------------------------------------------


async def test_restart_fails_runs_whose_task_is_gone(tmp_path: Path):
    async with api(tmp_path) as (client, app):
        orphan = await insert_run(app, agno_run_id="lost-when-the-server-stopped")
        await app.state.research_service.reconcile_after_restart()
        detail = (await client.get(f"{API}/{orphan}")).json()
        assert detail["status"] == "failed" and detail["error"] == RESTART_ERROR


async def test_restart_saves_runs_that_finished_before_the_restart(tmp_path: Path):
    """A run finishes in Agno, but the server stops before anyone polls. The next start saves it."""
    async with api(tmp_path) as (client, app):
        run_id = (await client.post(API, json={"query": "Notion"})).json()["id"]
        workflow = app.state.research_service.workflow
        async with app.state.database.session() as session:
            agno_run_id = (await ResearchRunRepository(session).get(uuid.UUID(run_id))).agno_run_id
        for _ in range(300):
            run = await workflow.aget_run(agno_run_id, session_id=run_id)
            if run is not None and str(getattr(run.status, "value", run.status)) == "COMPLETED":
                break
            await asyncio.sleep(0.05)

    async with api(tmp_path) as (client, app):  # "restarted" app on the same database files
        async with app.router.lifespan_context(app):  # startup runs reconcile_after_restart
            async with app.state.database.session() as session:
                saved = await ResearchRunRepository(session).get(uuid.UUID(run_id))
            assert saved.status == RunStatus.SUCCEEDED and saved.report is not None


async def test_run_that_never_got_an_agno_id_fails_after_a_grace_period(tmp_path: Path):
    async with api(tmp_path) as (client, app):
        old = datetime.now(UTC) - timedelta(minutes=5)
        stuck = await insert_run(app, created_at=old)
        fresh = await insert_run(app)
        listing = {i["id"]: i["status"] for i in (await client.get(API)).json()["items"]}
        assert listing[str(stuck)] == "failed" and listing[str(fresh)] == "running"


async def test_cancelled_agno_run_is_failed(tmp_path: Path, monkeypatch):
    async with api(tmp_path) as (client, app):
        run_id = await insert_run(app, agno_run_id="r1")

        async def cancelled_run(run_id, session_id=None):
            return SimpleNamespace(status="CANCELLED", step_results=[])

        monkeypatch.setattr(app.state.research_service.workflow, "aget_run", cancelled_run)
        detail = (await client.get(f"{API}/{run_id}")).json()
        assert detail["status"] == "failed" and detail["error"] == "The run was cancelled."


async def test_reconcile_survives_unreadable_agno_runs(tmp_path: Path, monkeypatch):
    async with api(tmp_path) as (client, app):
        run_id = await insert_run(app, agno_run_id="r1")

        async def broken(run_id, session_id=None):
            raise RuntimeError("agno db down")

        monkeypatch.setattr(app.state.research_service.workflow, "aget_run", broken)
        response = await client.get(f"{API}/{run_id}")
        assert response.status_code == 200 and response.json()["status"] == "running"
