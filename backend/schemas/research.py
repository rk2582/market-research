"""Internal data shapes for research runs and sources (returned by repositories).

The public API request/response models live in schemas/api.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from db.models.research import InputType, RetrievedBy, RunMode, RunStatus

MAX_EXCERPT_CHARS = 6000  # = tools.web_research.PAGE_TEXT_CHARS: the fact-checker sees what the researcher saw


class ResearchRunCreate(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    input_type: InputType
    company_name: str | None = Field(default=None, max_length=255)
    website_url: str | None = None
    mode: RunMode = RunMode.COMPANY
    scope: dict[str, Any] | None = None


class ConfirmedCompetitor(BaseModel):
    """A competitor the user confirmed for a run (passed to the workflow and stored in run_competitors)."""

    name: str
    website: str | None = None
    added_by_user: bool = False


class RunTotals(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)


class ResearchRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    input_type: InputType
    company_name: str | None
    website_url: str | None
    company_id: uuid.UUID | None = None
    mode: RunMode = RunMode.COMPANY
    scope: dict[str, Any] | None = None
    status: RunStatus
    error: str | None
    current_step: str | None
    agno_run_id: str | None
    report: dict[str, Any] | None
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    duration_ms: int | None
    created_at: datetime
    finished_at: datetime | None
    updated_at: datetime


class SourceCreate(BaseModel):
    url: str = Field(min_length=1)
    title: str | None = None
    excerpt: str | None = None
    retrieved_by: RetrievedBy

    @field_validator("title")
    @classmethod
    def _trim_title(cls, value: str | None) -> str | None:
        return value[:500] if value else value

    @field_validator("excerpt")
    @classmethod
    def _cap_excerpt(cls, value: str | None) -> str | None:
        """Store short excerpts only (enough to fact-check claims; keeps prompts and storage small)."""
        return value[:MAX_EXCERPT_CHARS] if value else value


class Source(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_run_id: uuid.UUID
    ref_number: int
    url: str
    title: str | None
    excerpt: str | None
    retrieved_by: RetrievedBy
    retrieved_at: datetime
