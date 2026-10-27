"""Alembic environment: runs migrations for OUR product tables only.

- The URL comes from backend/.env (DATABASE_URL), unless a caller sets `sqlalchemy.url`
  (the integration tests do this to migrate a temporary database).
- Agno's own tables live in a separate schema and are never touched by our migrations.

Usage (from backend/):
    uv run alembic upgrade head                       # apply all migrations
    uv run alembic revision --autogenerate -m "..."   # create a new migration from model changes
    uv run alembic check                              # fail if models and migrations differ
"""

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import db.models  # noqa: F401  (registers all tables on Base.metadata)
from core.config import get_settings
from db.base import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def include_object(obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    """Ignore anything Agno owns, even if it ever ends up in our schema."""
    if type_ == "table" and name and name.startswith("agno_"):
        return False
    return True


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        include_schemas=False,  # only the default (public) schema; Agno uses its own schema
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) mode is not supported; run against a database.")

asyncio.run(run_migrations_online())
