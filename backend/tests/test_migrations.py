"""Migration tests against real PostgreSQL, in a TEMPORARY database.

Your real `market360` database is never touched: each test session creates
`market360_test_<random>`, runs migrations there, and drops it afterwards.
Needs a PostgreSQL user allowed to create databases (the `postgres` user is).

Run with:  uv run pytest -m integration
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import Settings, get_settings
from tests.conftest import make_settings

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _admin_conninfo(async_url: str) -> str:
    """psycopg connection string for the 'postgres' maintenance database, same server/credentials."""
    url = make_url(async_url).set(drivername="postgresql", database="postgres")
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def temp_db_url() -> Iterator[str]:
    get_settings.cache_clear()
    real_url = get_settings().database_url
    get_settings.cache_clear()
    name = f"market360_test_{secrets.token_hex(4)}"
    try:
        with psycopg.connect(_admin_conninfo(real_url), autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')  # name is generated above, not user input
    except psycopg.errors.InsufficientPrivilege:  # pragma: no cover
        pytest.skip("DB user in .env cannot CREATE DATABASE; use the 'postgres' user for integration tests")
    try:
        yield make_url(real_url).set(database=name).render_as_string(hide_password=False)
    finally:
        with psycopg.connect(_admin_conninfo(real_url), autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _alembic(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))  # configparser escaping
    cfg.attributes["configure_logger"] = False
    return cfg


async def _public_tables(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            )
            return {r[0] for r in rows}
    finally:
        await engine.dispose()


def test_upgrade_check_downgrade_cycle(temp_db_url: str):
    cfg = _alembic(temp_db_url)

    command.upgrade(cfg, "head")
    assert {"research_runs", "research_sources"} <= asyncio.run(_public_tables(temp_db_url))

    command.check(cfg)  # raises if the models and the migrations disagree

    command.downgrade(cfg, "base")
    assert asyncio.run(_public_tables(temp_db_url)) == {"alembic_version"}

    command.upgrade(cfg, "head")  # and back up again


def test_agno_tables_are_ignored_by_migrations(temp_db_url: str, tmp_path: Path):
    """Start the real app (AgentOS creates its tables in the 'agno' schema), then check
    that Alembic still sees no differences — it must never try to drop Agno's tables."""
    from main import create_app

    cfg = _alembic(temp_db_url)
    command.upgrade(cfg, "head")

    settings: Settings = make_settings(tmp_path, database_url=temp_db_url)
    app = create_app(settings)

    async def _start_and_stop() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(_start_and_stop())
    command.check(cfg)
