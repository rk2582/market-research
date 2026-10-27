"""create research tables

First product tables: research_runs (one per research request) and research_sources
(web pages used as evidence, numbered [1], [2] … in the report).

Revision ID: 65f008584804
Revises:
Create Date: 2026-10-21 17:07:58.412881
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "65f008584804"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("input_type", sa.String(length=8), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="running", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("agno_run_id", sa.String(length=64), nullable=True),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("input_type IN ('name', 'url')", name=op.f("ck_research_runs_input_type")),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')", name=op.f("ck_research_runs_status")
        ),
        sa.CheckConstraint("length(query) BETWEEN 2 AND 300", name=op.f("ck_research_runs_query_length")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_runs")),
    )
    op.create_index("ix_research_runs_agno_run_id", "research_runs", ["agno_run_id"], unique=False)
    op.create_index("ix_research_runs_created_at", "research_runs", ["created_at"], unique=False)
    op.create_index("ix_research_runs_status", "research_runs", ["status"], unique=False)
    op.create_table(
        "research_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("ref_number", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("retrieved_by", sa.String(length=16), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("retrieved_by IN ('search', 'extract')", name=op.f("ck_research_sources_retrieved_by")),
        sa.CheckConstraint("ref_number >= 1", name=op.f("ck_research_sources_ref_number_positive")),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name=op.f("fk_research_sources_research_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_sources")),
        sa.UniqueConstraint(
            "research_run_id", "ref_number", name=op.f("uq_research_sources_research_run_id_ref_number")
        ),
        sa.UniqueConstraint("research_run_id", "url", name=op.f("uq_research_sources_research_run_id_url")),
    )


def downgrade() -> None:
    op.drop_table("research_sources")
    op.drop_index("ix_research_runs_status", table_name="research_runs")
    op.drop_index("ix_research_runs_created_at", table_name="research_runs")
    op.drop_index("ix_research_runs_agno_run_id", table_name="research_runs")
    op.drop_table("research_runs")
