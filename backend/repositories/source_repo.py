"""Data access for research_sources (the evidence behind each report)."""

from __future__ import annotations

import builtins
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.research import ResearchSourceRow
from schemas.research import Source, SourceCreate


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_many(self, run_id: uuid.UUID, sources: builtins.list[SourceCreate]) -> builtins.list[Source]:
        """Add sources to a run, numbering them [1], [2] … in the order given.

        A URL already stored for this run is skipped (it keeps its original number), so the same
        page found twice is cited once. Returns only the newly added sources.
        """
        existing = set(
            await self.session.scalars(select(ResearchSourceRow.url).where(ResearchSourceRow.research_run_id == run_id))
        )
        max_ref = await self.session.scalar(
            select(func.max(ResearchSourceRow.ref_number)).where(ResearchSourceRow.research_run_id == run_id)
        )
        next_ref = int(max_ref or 0) + 1

        new_rows: builtins.list[ResearchSourceRow] = []
        for source in sources:
            if source.url in existing:
                continue
            existing.add(source.url)
            new_rows.append(ResearchSourceRow(research_run_id=run_id, ref_number=next_ref, **source.model_dump()))
            next_ref += 1

        self.session.add_all(new_rows)
        await self.session.flush()
        for row in new_rows:
            await self.session.refresh(row)
        return [Source.model_validate(r) for r in new_rows]

    async def list_for_run(self, run_id: uuid.UUID) -> builtins.list[Source]:
        rows = await self.session.scalars(
            select(ResearchSourceRow)
            .where(ResearchSourceRow.research_run_id == run_id)
            .order_by(ResearchSourceRow.ref_number)
        )
        return [Source.model_validate(r) for r in rows]
