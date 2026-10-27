"""Database rules enforced by the tables themselves (checked on SQLite here, PostgreSQL in integration)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from db.models.research import ResearchRunRow, ResearchSourceRow
from db.session import Database


async def _insert_run(db: Database, **values) -> ResearchRunRow:
    row = ResearchRunRow(**{"query": "Notion", "input_type": "name", **values})
    async with db.session() as s:
        s.add(row)
    return row


@pytest.mark.parametrize(
    "values",
    [
        {"input_type": "company"},  # not name/url
        {"status": "queued"},  # not a known status
        {"query": "x"},  # too short
    ],
)
async def test_check_constraints_reject_bad_rows(database: Database, values):
    with pytest.raises(IntegrityError):
        await _insert_run(database, **values)


async def test_unique_ref_number_per_run(database: Database):
    run = await _insert_run(database)
    with pytest.raises(IntegrityError):
        async with database.session() as s:
            s.add_all(
                [
                    ResearchSourceRow(research_run_id=run.id, ref_number=1, url="https://a", retrieved_by="search"),
                    ResearchSourceRow(research_run_id=run.id, ref_number=1, url="https://b", retrieved_by="search"),
                ]
            )


async def test_deleting_a_run_deletes_its_sources(database: Database):
    run = await _insert_run(database)
    async with database.session() as s:
        s.add(ResearchSourceRow(research_run_id=run.id, ref_number=1, url="https://a", retrieved_by="search"))

    async with database.session() as s:
        await s.execute(text("DELETE FROM research_runs"))  # database-level cascade, not ORM

    async with database.session() as s:
        assert (await s.scalars(select(ResearchSourceRow))).all() == []
