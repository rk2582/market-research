"""Checks against the local PostgreSQL configured in backend/.env.

Run with:  uv run pytest -m integration
"""

import httpx
import pytest
from sqlalchemy import text

from core.config import Settings, get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def real_settings() -> Settings:
    get_settings.cache_clear()
    try:
        settings = get_settings()
    except Exception as exc:  # pragma: no cover - only when .env is missing/invalid
        pytest.fail(f"backend/.env missing or invalid — copy .env.example to .env and fill it in ({exc})")
    if not settings.database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("DATABASE_URL in backend/.env must point at PostgreSQL for integration tests")
    yield settings
    get_settings.cache_clear()


async def test_postgres_version_is_supported(real_settings: Settings):
    from db.session import Database

    db = Database(real_settings.database_url)
    try:
        async with db.engine.connect() as conn:
            server_version = (await conn.execute(text("SHOW server_version"))).scalar_one()
    finally:
        await db.dispose()
    assert int(server_version.split(".")[0]) >= 14, f"PostgreSQL {server_version} found; 14+ required"


async def test_full_app_against_postgres(real_settings: Settings):
    from main import create_app

    app = create_app(real_settings)
    async with app.router.lifespan_context(app):  # runs AgentOS startup: creates Agno tables
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/v1/health")
            assert r.status_code == 200, r.text
            assert r.json() == {"status": "ok", "database": "ok"}

        async with app.state.database.engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = :schema"),
                {"schema": real_settings.agno_db_schema},
            )
            agno_tables = {row[0] for row in rows}
    assert "agno_sessions" in agno_tables


async def test_research_api_end_to_end_on_postgres(real_settings: Settings):
    """Start (with a confirmed company and competitors) → poll → report on real PostgreSQL: JSONB report,
    sources, run_competitors, companies and Agno's own schema. OpenAI and Tavily are fakes, so this costs
    nothing. The test removes the rows it created (its company uses a test-only website)."""
    import asyncio
    import uuid

    from pydantic import SecretStr

    from main import create_app
    from tests.fakes import FakeOpenAI
    from tests.test_research_workflow import happy_script, notion_tavily

    settings = real_settings.model_copy(
        update={"openai_api_key": SecretStr("sk-test"), "tavily_api_key": SecretStr("tvly-test")}
    )
    openai = FakeOpenAI(happy_script())
    app = create_app(settings, http_client=openai.client, tavily_client=notion_tavily())
    run_id = None
    test_domain = "notion-integration-test.example"
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                started = await client.post(
                    "/api/v1/research",
                    json={
                        "query": "Notion",
                        "company": {"name": "Notion", "website": f"https://{test_domain}"},
                        "competitors": [{"name": "Coda"}, {"name": "Confluence", "added_by_user": True}],
                    },
                )
                assert started.status_code == 202, started.text
                run_id = started.json()["id"]
                for _ in range(300):
                    detail = (await client.get(f"/api/v1/research/{run_id}")).json()
                    if detail["status"] != "running":
                        break
                    await asyncio.sleep(0.1)
                assert detail["status"] == "succeeded", detail
                report = await client.get(f"/api/v1/research/{run_id}/report")
                assert report.status_code == 200 and report.json()["references"]
                async with app.state.database.engine.connect() as conn:
                    count = (
                        await conn.execute(
                            text("SELECT count(*) FROM research_sources WHERE research_run_id = :id"),
                            {"id": uuid.UUID(run_id)},
                        )
                    ).scalar_one()
                    competitors = (
                        await conn.execute(
                            text(
                                "SELECT name, origin FROM run_competitors WHERE research_run_id = :id ORDER BY position"
                            ),
                            {"id": uuid.UUID(run_id)},
                        )
                    ).all()
                    company = (
                        await conn.execute(
                            text(
                                "SELECT c.domain, c.last_researched_at FROM research_runs r"
                                " JOIN companies c ON c.id = r.company_id WHERE r.id = :id"
                            ),
                            {"id": uuid.UUID(run_id)},
                        )
                    ).one()
                assert count == len(report.json()["references"])
                assert [tuple(r) for r in competitors] == [("Coda", "suggested"), ("Confluence", "added")]
                assert company.domain == test_domain and company.last_researched_at is not None
            finally:
                if run_id:  # leave the developer's database as it was
                    async with app.state.database.engine.begin() as conn:
                        await conn.execute(text("DELETE FROM research_runs WHERE id = :id"), {"id": uuid.UUID(run_id)})
                        await conn.execute(text("DELETE FROM companies WHERE domain = :d"), {"d": test_domain})
                    app.state.agent_os.db.delete_session(run_id)


async def test_market_run_mode_and_scope_round_trip_on_postgres(real_settings: Settings):
    """M13: a market run's mode and JSONB scope are stored and read back on real PostgreSQL."""
    from db.models.research import InputType, RunMode
    from db.session import Database
    from repositories.research_repo import ResearchRunRepository
    from schemas.research import ResearchRunCreate

    database = Database(real_settings.database_url)
    run_id = None
    try:
        async with database.session() as session:
            run = await ResearchRunRepository(session).create(
                ResearchRunCreate(
                    query="Milk",
                    input_type=InputType.NAME,
                    company_name="Fresh packaged milk · Kerala",
                    mode=RunMode.MARKET,
                    scope={"product": "Fresh packaged milk", "region": "Kerala", "customer_type": None},
                )
            )
            run_id = run.id
        async with database.session() as session:
            loaded = await ResearchRunRepository(session).get(run_id)
        assert loaded is not None and loaded.mode == RunMode.MARKET
        assert loaded.scope == {"product": "Fresh packaged milk", "region": "Kerala", "customer_type": None}
    finally:
        if run_id:
            async with database.engine.begin() as conn:
                await conn.execute(text("DELETE FROM research_runs WHERE id = :id"), {"id": run_id})
        await database.dispose()


async def test_second_research_round_on_postgres(real_settings: Settings):
    """M14: the optional second round runs inside an Agno Condition; its merged evidence must survive Agno's
    PostgreSQL storage (nested step results) so the report, totals and stored sources include it."""
    import asyncio
    import uuid

    from pydantic import SecretStr

    from main import create_app
    from tests.fakes import FakeOpenAI, tool_call
    from tests.test_m13_market import MILK
    from tests.test_m14_research_more import COSTS, gap_answer, second_round_script, second_round_tavily

    settings = real_settings.model_copy(
        update={
            "openai_api_key": SecretStr("sk-test"),
            "tavily_api_key": SecretStr("tvly-test"),
            "research_more_enabled": True,
        }
    )
    openai = FakeOpenAI(second_round_script([[tool_call("search_web", query="Kerala dairy plant cost")], gap_answer]))
    app = create_app(settings, http_client=openai.client, tavily_client=second_round_tavily())
    run_id = None
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                run_id = (await client.post("/api/v1/research", json=MILK)).json()["id"]
                for _ in range(300):
                    detail = (await client.get(f"/api/v1/research/{run_id}")).json()
                    if detail["status"] != "running":
                        break
                    await asyncio.sleep(0.1)
                assert detail["status"] == "succeeded", detail
                report = (await client.get(f"/api/v1/research/{run_id}/report")).json()
                assert report["meta"]["second_round"]["filled"] == 3
                deepen = next(u for u in report["meta"]["usage"] if u["step"] == "deepen")
                assert detail["totals"]["total_tokens"] >= deepen["total_tokens"] > 0
                async with app.state.database.engine.connect() as conn:
                    excerpt = (
                        await conn.execute(
                            text("SELECT excerpt FROM research_sources WHERE research_run_id = :id AND url = :url"),
                            {"id": uuid.UUID(run_id), "url": COSTS},
                        )
                    ).scalar_one()
                assert excerpt  # round-2 page stored with the text it was checked against
            finally:
                if run_id:
                    async with app.state.database.engine.begin() as conn:
                        await conn.execute(text("DELETE FROM research_runs WHERE id = :id"), {"id": uuid.UUID(run_id)})
                    app.state.agent_os.db.delete_session(run_id)
