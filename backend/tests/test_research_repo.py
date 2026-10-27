import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.research import InputType, RunStatus
from repositories.research_repo import ResearchRunRepository
from schemas.research import ResearchRunCreate, RunTotals


def _new(query: str = "Notion", **overrides) -> ResearchRunCreate:
    values = {"query": query, "input_type": InputType.NAME, **overrides}
    return ResearchRunCreate(**values)


async def test_create_sets_defaults(session: AsyncSession):
    run = await ResearchRunRepository(session).create(_new(website_url=None))
    assert isinstance(run.id, uuid.UUID)
    assert run.status == RunStatus.RUNNING
    assert run.total_tokens == 0
    assert run.report is None and run.finished_at is None
    assert run.created_at is not None and run.updated_at is not None


async def test_get_returns_none_for_unknown_id(session: AsyncSession):
    assert await ResearchRunRepository(session).get(uuid.uuid4()) is None


async def test_get_round_trip(session: AsyncSession):
    repo = ResearchRunRepository(session)
    created = await repo.create(
        _new("https://www.notion.so", input_type=InputType.URL, website_url="https://www.notion.so")
    )
    fetched = await repo.get(created.id)
    assert fetched == created


async def test_list_recent_is_newest_first_with_total_and_paging(session: AsyncSession):
    repo = ResearchRunRepository(session)
    ids = [(await repo.create(_new(f"Company {i}"))).id for i in range(3)]
    # SQLite timestamps have 1-second resolution; set distinct created_at values explicitly.
    from datetime import UTC, datetime, timedelta

    from db.models.research import ResearchRunRow

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i, run_id in enumerate(ids):
        (await session.get(ResearchRunRow, run_id)).created_at = base + timedelta(minutes=i)
    await session.flush()

    items, total = await repo.list_recent(limit=2, offset=0)
    assert total == 3
    assert [r.query for r in items] == ["Company 2", "Company 1"]
    items, _ = await repo.list_recent(limit=2, offset=2)
    assert [r.query for r in items] == ["Company 0"]


async def test_status_queries(session: AsyncSession):
    repo = ResearchRunRepository(session)
    alpha = await repo.create(_new("Alpha"))
    await repo.create(_new("Beta"))
    await repo.finish(alpha.id, status=RunStatus.FAILED, error="boom")

    assert await repo.count_by_status(RunStatus.RUNNING) == 1
    assert [r.query for r in await repo.list_by_status(RunStatus.RUNNING)] == ["Beta"]
    assert [r.query for r in await repo.list_by_status(RunStatus.FAILED)] == ["Alpha"]


async def test_set_agno_run_id(session: AsyncSession):
    repo = ResearchRunRepository(session)
    run = await repo.create(_new())
    updated = await repo.set_agno_run_id(run.id, "agno-run-123")
    assert updated is not None and updated.agno_run_id == "agno-run-123"
    assert await repo.set_agno_run_id(uuid.uuid4(), "x") is None


async def test_finish_records_outcome(session: AsyncSession):
    repo = ResearchRunRepository(session)
    run = await repo.create(_new())
    report = {"meta": {"partial": False}, "executive_summary": "…"}
    done = await repo.finish(
        run.id,
        status=RunStatus.SUCCEEDED,
        report=report,
        totals=RunTotals(input_tokens=1000, output_tokens=250, total_tokens=1250, duration_ms=95_000),
        company_name="Notion Labs",
    )
    assert done is not None
    assert done.status == RunStatus.SUCCEEDED
    assert done.report == report
    assert (done.total_input_tokens, done.total_output_tokens, done.total_tokens) == (1000, 250, 1250)
    assert done.duration_ms == 95_000
    assert done.company_name == "Notion Labs"
    assert done.finished_at is not None


async def test_finish_without_totals_keeps_zero_counts(session: AsyncSession):
    repo = ResearchRunRepository(session)
    run = await repo.create(_new(company_name="Kept"))
    done = await repo.finish(run.id, status=RunStatus.FAILED, error="Researcher timed out")
    assert done is not None and done.total_tokens == 0 and done.error == "Researcher timed out"
    assert done.company_name == "Kept"  # not overwritten when company_name isn't given


async def test_finish_rejects_running_status(session: AsyncSession):
    repo = ResearchRunRepository(session)
    run = await repo.create(_new())
    with pytest.raises(ValueError, match="final status"):
        await repo.finish(run.id, status=RunStatus.RUNNING)


async def test_finish_unknown_run_returns_none(session: AsyncSession):
    assert await ResearchRunRepository(session).finish(uuid.uuid4(), status=RunStatus.FAILED) is None


@pytest.mark.parametrize("query", ["", "x", "y" * 301])
def test_create_schema_validates_query_length(query: str):
    with pytest.raises(ValidationError):
        _new(query)
