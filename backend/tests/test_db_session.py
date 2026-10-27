from pathlib import Path

import pytest
from agno.db.postgres import PostgresDb
from agno.db.sqlite import SqliteDb
from sqlalchemy import text

from core.agno_db import AGNO_DB_ID, build_agno_db
from db.session import Database
from tests.conftest import make_settings


@pytest.fixture
async def database(tmp_path: Path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    async with db.engine.begin() as conn:
        await conn.execute(text("CREATE TABLE notes (body TEXT)"))
    yield db
    await db.dispose()


async def _count(db: Database) -> int:
    async with db.engine.connect() as conn:
        return (await conn.execute(text("SELECT COUNT(*) FROM notes"))).scalar_one()


async def test_session_commits_on_success(database: Database):
    async with database.session() as session:
        await session.execute(text("INSERT INTO notes VALUES ('kept')"))
    assert await _count(database) == 1


async def test_session_rolls_back_on_error(database: Database):
    with pytest.raises(RuntimeError):
        async with database.session() as session:
            await session.execute(text("INSERT INTO notes VALUES ('lost')"))
            raise RuntimeError("fail mid-transaction")
    assert await _count(database) == 0


def test_agno_db_is_postgres_in_its_own_schema(tmp_path: Path):
    settings = make_settings(tmp_path, database_url="postgresql+asyncpg://u:p@localhost:5432/market360")
    agno_db = build_agno_db(settings)  # builds the engine only; does not connect
    assert isinstance(agno_db, PostgresDb)
    assert agno_db.id == AGNO_DB_ID
    assert agno_db.db_schema == "agno"


def test_agno_db_is_sqlite_for_tests(settings):
    assert isinstance(build_agno_db(settings), SqliteDb)
