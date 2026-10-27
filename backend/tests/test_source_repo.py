import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.research import InputType, RetrievedBy
from db.session import Database
from repositories.research_repo import ResearchRunRepository
from repositories.source_repo import SourceRepository
from schemas.research import MAX_EXCERPT_CHARS, ResearchRunCreate, SourceCreate


async def _run_id(session: AsyncSession) -> uuid.UUID:
    run = await ResearchRunRepository(session).create(ResearchRunCreate(query="Notion", input_type=InputType.NAME))
    return run.id


def _src(url: str, by: RetrievedBy = RetrievedBy.SEARCH, **kw) -> SourceCreate:
    return SourceCreate(url=url, retrieved_by=by, **kw)


async def test_sources_are_numbered_in_order(session: AsyncSession):
    run_id = await _run_id(session)
    added = await SourceRepository(session).add_many(
        run_id, [_src("https://a.example", title="A"), _src("https://b.example", RetrievedBy.EXTRACT)]
    )
    assert [(s.ref_number, s.url) for s in added] == [(1, "https://a.example"), (2, "https://b.example")]
    assert added[1].retrieved_by == RetrievedBy.EXTRACT
    assert added[0].retrieved_at is not None


async def test_duplicate_urls_are_skipped_and_numbering_continues(session: AsyncSession):
    run_id = await _run_id(session)
    repo = SourceRepository(session)
    await repo.add_many(run_id, [_src("https://a.example"), _src("https://a.example")])  # duplicate in one batch
    added = await repo.add_many(run_id, [_src("https://a.example"), _src("https://c.example")])  # dup across batches

    assert [(s.ref_number, s.url) for s in added] == [(2, "https://c.example")]
    assert [s.ref_number for s in await repo.list_for_run(run_id)] == [1, 2]


async def test_numbering_is_per_run(session: AsyncSession):
    repo = SourceRepository(session)
    run_a, run_b = await _run_id(session), await _run_id(session)
    await repo.add_many(run_a, [_src("https://a.example")])
    added_b = await repo.add_many(run_b, [_src("https://a.example")])  # same URL, other run: allowed
    assert added_b[0].ref_number == 1


async def test_list_for_run_is_ordered_and_empty_for_unknown_run(session: AsyncSession):
    run_id = await _run_id(session)
    repo = SourceRepository(session)
    await repo.add_many(run_id, [_src(f"https://{n}.example") for n in "xyz"])
    assert [s.ref_number for s in await repo.list_for_run(run_id)] == [1, 2, 3]
    assert await repo.list_for_run(uuid.uuid4()) == []


async def test_add_many_with_empty_list(session: AsyncSession):
    assert await SourceRepository(session).add_many(await _run_id(session), []) == []


def test_excerpt_and_title_are_capped():
    src = _src("https://a.example", title="t" * 600, excerpt="e" * (MAX_EXCERPT_CHARS + 500))
    assert src.title is not None and len(src.title) == 500
    assert src.excerpt is not None and len(src.excerpt) == MAX_EXCERPT_CHARS
    assert _src("https://a.example").excerpt is None


async def test_source_for_unknown_run_is_rejected_by_foreign_key(database: Database):
    with pytest.raises(IntegrityError):
        async with database.session() as s:  # own session: it is rolled back by the error
            await SourceRepository(s).add_many(uuid.uuid4(), [_src("https://a.example")])
