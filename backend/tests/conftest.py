"""Shared test fixtures.

Tests never read backend/.env: settings are built explicitly, pointing at a throwaway
SQLite file, so they run without PostgreSQL, network or API keys.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

import db.models  # noqa: F401  (registers all tables on Base.metadata)
from core.config import Settings
from db.base import Base
from db.session import Database


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    # The M14 second round is off unless a test turns it on (keeps the older tests' fake scripts exact).
    values: dict[str, object] = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        "research_more_enabled": False,
        "parallel_research_enabled": False,  # M15: same reason
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    """A fresh SQLite database with all product tables (created from the models, like the orchestrator)."""
    db = Database(settings.database_url)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield db
    await db.dispose()


@pytest.fixture
async def session(database: Database) -> AsyncIterator[AsyncSession]:
    """One session per test; committed at the end like a real request."""
    async with database.session() as s:
        yield s


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    from main import create_app

    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    # raise_app_exceptions=False: let the app's 500 handler produce the response, as in production.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
