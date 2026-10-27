"""Agno's own storage (workflow runs, sessions, metrics).

Agno manages these tables itself, in a separate schema ("agno" by default), so they never mix
with our Alembic-managed product tables.
"""

from __future__ import annotations

from agno.db.base import BaseDb
from agno.db.postgres import PostgresDb
from agno.db.sqlite import SqliteDb

from core.config import Settings

AGNO_DB_ID = "market360-agno"


def build_agno_db(settings: Settings) -> BaseDb:
    url = settings.agno_db_url
    if url.startswith("sqlite"):  # tests
        return SqliteDb(id=AGNO_DB_ID, db_url=url)
    return PostgresDb(id=AGNO_DB_ID, db_url=url, db_schema=settings.agno_db_schema)
