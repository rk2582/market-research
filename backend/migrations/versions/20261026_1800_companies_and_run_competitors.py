"""M12: companies, run competitors, run mode and scope.

- companies: one row per company, shared by its runs (matched by website domain when known).
- run_competitors: the competitors the user confirmed for a run, in order.
- research_runs: company_id, mode (company | market) and scope (market mode, M13).

Revision ID: 05bb7f0bf796
Revises: 3b1c9e2d7a40
Create Date: 2026-10-26 17:57:12.597808
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "05bb7f0bf796"
down_revision: str | Sequence[str] | None = "3b1c9e2d7a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_researched_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("domain", name="uq_companies_domain"),
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=False)
    op.create_table(
        "run_competitors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.CheckConstraint("origin IN ('suggested', 'added')", name=op.f("ck_run_competitors_origin")),
        sa.CheckConstraint("position >= 1", name=op.f("ck_run_competitors_position_positive")),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name=op.f("fk_run_competitors_research_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_competitors")),
        sa.UniqueConstraint("research_run_id", "position", name=op.f("uq_run_competitors_research_run_id_position")),
    )
    op.add_column("research_runs", sa.Column("company_id", sa.Uuid(), nullable=True))
    op.add_column("research_runs", sa.Column("mode", sa.String(length=16), server_default="company", nullable=False))
    op.add_column(
        "research_runs",
        sa.Column(
            "scope", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True
        ),
    )
    op.create_check_constraint(op.f("ck_research_runs_mode"), "research_runs", "mode IN ('company', 'market')")
    op.create_index("ix_research_runs_company_id", "research_runs", ["company_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_research_runs_company_id_companies"),
        "research_runs",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_research_runs_company_id_companies"), "research_runs", type_="foreignkey")
    op.drop_index("ix_research_runs_company_id", table_name="research_runs")
    op.drop_constraint(op.f("ck_research_runs_mode"), "research_runs", type_="check")
    op.drop_column("research_runs", "scope")
    op.drop_column("research_runs", "mode")
    op.drop_column("research_runs", "company_id")
    op.drop_table("run_competitors")
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_table("companies")
