import httpx
from fastapi import FastAPI

from db.session import Database, get_database


async def test_health_ok_when_database_reachable(client: httpx.AsyncClient):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


async def test_health_503_when_database_unreachable(app: FastAPI, client: httpx.AsyncClient):
    class DownDatabase:
        async def ping(self) -> bool:
            return False

    app.dependency_overrides[get_database] = lambda: DownDatabase()
    r = await client.get("/api/v1/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "database": "error"}


async def test_ping_returns_false_for_bad_database(tmp_path):
    # A directory that doesn't exist: SQLite cannot open the file.
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'missing' / 'x.db'}")
    try:
        assert await db.ping() is False
    finally:
        await db.dispose()


async def test_ping_returns_false_on_timeout(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    try:
        assert await db.ping(timeout_s=0) is False
    finally:
        await db.dispose()
