"""Product tables: one row per research run, plus the web sources it used."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

# JSONB on PostgreSQL, plain JSON on SQLite (tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class InputType(StrEnum):
    NAME = "name"
    URL = "url"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"  # some later steps failed; a partial report exists
    FAILED = "failed"


TERMINAL_STATUSES = frozenset({RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED})


class RunMode(StrEnum):
    COMPANY = "company"  # one company and its competitors
    MARKET = "market"  # a product or business idea in a region (market-entry report, M13)


class CompetitorOrigin(StrEnum):
    SUGGESTED = "suggested"  # suggested by the Identifier and kept by the user
    ADDED = "added"  # added by the user on the confirm screen


class RetrievedBy(StrEnum):
    SEARCH = "search"  # Tavily web_search_using_tavily
    EXTRACT = "extract"  # Tavily extract_url_content


def _in_list(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


class CompanyRow(Base):
    """One row per company researched, shared by all its runs (history and comparison need this)."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))  # "notion.so" (no www.); the matching key when known
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("domain", name="uq_companies_domain"),
        Index("ix_companies_name", "name"),
    )


class ResearchRunRow(Base):
    __tablename__ = "research_runs"

    # Also used as the Agno session_id for this run.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    input_type: Mapped[str] = mapped_column(String(8), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    website_url: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default=RunMode.COMPANY.value)
    scope: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # market mode: product, region, customer_type
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=RunStatus.RUNNING.value)
    error: Mapped[str | None] = mapped_column(Text)
    current_step: Mapped[str | None] = mapped_column(String(16))  # workflow step now running (progress)
    agno_run_id: Mapped[str | None] = mapped_column(String(64))
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    total_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sources: Mapped[list[ResearchSourceRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    competitors: Mapped[list[RunCompetitorRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True, order_by="RunCompetitorRow.position"
    )

    __table_args__ = (
        CheckConstraint(_in_list("input_type", InputType), name="input_type"),
        CheckConstraint(_in_list("status", RunStatus), name="status"),
        CheckConstraint(_in_list("mode", RunMode), name="mode"),
        CheckConstraint("length(query) BETWEEN 2 AND 300", name="query_length"),
        Index("ix_research_runs_created_at", "created_at"),
        Index("ix_research_runs_status", "status"),
        Index("ix_research_runs_agno_run_id", "agno_run_id"),
        Index("ix_research_runs_company_id", "company_id"),
    )


class RunCompetitorRow(Base):
    """The competitors the user confirmed for a run, in their order."""

    __tablename__ = "run_competitors"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, … as shown to the user
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)

    run: Mapped[ResearchRunRow] = relationship(back_populates="competitors")

    __table_args__ = (
        UniqueConstraint("research_run_id", "position"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint(_in_list("origin", CompetitorOrigin), name="origin"),
    )


class ResearchSourceRow(Base):
    __tablename__ = "research_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    ref_number: Mapped[int] = mapped_column(Integer, nullable=False)  # [1], [2] … in the report
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    excerpt: Mapped[str | None] = mapped_column(Text)
    retrieved_by: Mapped[str] = mapped_column(String(16), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[ResearchRunRow] = relationship(back_populates="sources")

    __table_args__ = (
        UniqueConstraint("research_run_id", "url"),
        UniqueConstraint("research_run_id", "ref_number"),
        CheckConstraint("ref_number >= 1", name="ref_number_positive"),
        CheckConstraint(_in_list("retrieved_by", RetrievedBy), name="retrieved_by"),
    )
