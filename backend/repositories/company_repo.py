"""Data access for companies and the competitors confirmed for a run. Takes an AsyncSession."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.research import CompanyRow, CompetitorOrigin, ResearchRunRow, RunCompetitorRow
from schemas.research import ConfirmedCompetitor


def domain_of(website: str | None) -> str | None:
    """'https://www.Notion.so/pricing' → 'notion.so'."""
    if not website:
        return None
    host = website.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    return host.removeprefix("www.") or None


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_or_create(self, name: str, website: str | None) -> uuid.UUID:
        """The same company is reused across runs: matched by website domain when known, else by name."""
        domain = domain_of(website)
        row: CompanyRow | None = None
        if domain:
            row = await self.session.scalar(select(CompanyRow).where(CompanyRow.domain == domain))
        if row is None:
            by_name = select(CompanyRow).where(func.lower(CompanyRow.name) == name.strip().lower())
            if domain:  # a same-named company with a different website is a different company
                by_name = by_name.where(CompanyRow.domain.is_(None))
            row = await self.session.scalar(by_name.order_by(CompanyRow.created_at).limit(1))
            if row is not None and domain:
                row.domain = domain  # learnt the website now
        if row is None:
            row = CompanyRow(name=name.strip()[:255], domain=domain)
            self.session.add(row)
        await self.session.flush()
        return row.id

    async def link_run(self, run_id: uuid.UUID, company_id: uuid.UUID, *, researched: bool = False) -> None:
        await self.session.execute(
            update(ResearchRunRow).where(ResearchRunRow.id == run_id).values(company_id=company_id)
        )
        if researched:
            await self.session.execute(
                update(CompanyRow).where(CompanyRow.id == company_id).values(last_researched_at=datetime.now(UTC))
            )

    async def add_competitors(self, run_id: uuid.UUID, competitors: list[ConfirmedCompetitor]) -> None:
        for position, competitor in enumerate(competitors, start=1):
            self.session.add(
                RunCompetitorRow(
                    research_run_id=run_id,
                    position=position,
                    name=competitor.name[:255],
                    website=competitor.website,
                    origin=CompetitorOrigin.ADDED if competitor.added_by_user else CompetitorOrigin.SUGGESTED,
                )
            )
        await self.session.flush()

    async def competitors_for(self, run_id: uuid.UUID) -> list[ConfirmedCompetitor]:
        rows = await self.session.scalars(
            select(RunCompetitorRow)
            .where(RunCompetitorRow.research_run_id == run_id)
            .order_by(RunCompetitorRow.position)
        )
        return [
            ConfirmedCompetitor(name=r.name, website=r.website, added_by_user=r.origin == CompetitorOrigin.ADDED)
            for r in rows
        ]
