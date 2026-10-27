"""Data access for research_runs. Takes an AsyncSession; the caller owns the transaction."""

from __future__ import annotations

import builtins
import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.research import ResearchRunRow, RunStatus
from schemas.research import ResearchRun, ResearchRunCreate, RunTotals


class ResearchRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: ResearchRunCreate) -> ResearchRun:
        row = ResearchRunRow(**data.model_dump(), status=RunStatus.RUNNING)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)  # load server defaults (timestamps, token counters)
        return ResearchRun.model_validate(row)

    async def get(self, run_id: uuid.UUID) -> ResearchRun | None:
        row = await self.session.get(ResearchRunRow, run_id)
        return ResearchRun.model_validate(row) if row else None

    async def list_recent(self, limit: int = 20, offset: int = 0) -> tuple[builtins.list[ResearchRun], int]:
        """Newest first, plus the total count (for paging)."""
        rows = await self.session.scalars(
            select(ResearchRunRow).order_by(ResearchRunRow.created_at.desc()).limit(limit).offset(offset)
        )
        total = await self.session.scalar(select(func.count()).select_from(ResearchRunRow))
        return [ResearchRun.model_validate(r) for r in rows], int(total or 0)

    async def list_by_status(self, status: RunStatus) -> builtins.list[ResearchRun]:
        rows = await self.session.scalars(select(ResearchRunRow).where(ResearchRunRow.status == status))
        return [ResearchRun.model_validate(r) for r in rows]

    async def count_by_status(self, status: RunStatus) -> int:
        count = await self.session.scalar(
            select(func.count()).select_from(ResearchRunRow).where(ResearchRunRow.status == status)
        )
        return int(count or 0)

    async def set_current_step(self, run_id: uuid.UUID, step: str) -> None:
        """Progress: record the step that just started. Ignored once the run has finished."""
        await self.session.execute(
            update(ResearchRunRow)
            .where(ResearchRunRow.id == run_id, ResearchRunRow.status == RunStatus.RUNNING)
            .values(current_step=step)
        )

    async def set_agno_run_id(self, run_id: uuid.UUID, agno_run_id: str) -> ResearchRun | None:
        return await self._update(run_id, agno_run_id=agno_run_id)

    async def finish(
        self,
        run_id: uuid.UUID,
        *,
        status: RunStatus,
        totals: RunTotals | None = None,
        report: dict[str, Any] | None = None,
        error: str | None = None,
        company_name: str | None = None,
    ) -> ResearchRun | None:
        """Record the final outcome of a run (succeeded / partial / failed)."""
        if status == RunStatus.RUNNING:
            raise ValueError("finish() needs a final status, not 'running'")
        totals = totals or RunTotals()
        values: dict[str, Any] = {
            "status": status,
            "report": report,
            "error": error,
            "total_input_tokens": totals.input_tokens,
            "total_output_tokens": totals.output_tokens,
            "total_tokens": totals.total_tokens,
            "duration_ms": totals.duration_ms,
            "current_step": None,
            "finished_at": func.now(),
        }
        if company_name is not None:
            values["company_name"] = company_name
        return await self._update(run_id, **values)

    async def _update(self, run_id: uuid.UUID, **values: Any) -> ResearchRun | None:
        row = await self.session.get(ResearchRunRow, run_id)
        if row is None:
            return None
        for key, value in values.items():
            setattr(row, key, value)
        await self.session.flush()
        await self.session.refresh(row)  # reload server-side values (finished_at, updated_at)
        return ResearchRun.model_validate(row)
