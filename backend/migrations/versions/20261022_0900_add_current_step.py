"""add current_step to research_runs

The workflow step that is running now (research, validate, analyse, strategise, write).
Written by the progress callback so the UI can show live progress; cleared when the run finishes.

Revision ID: 3b1c9e2d7a40
Revises: 65f008584804
Create Date: 2026-10-22 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3b1c9e2d7a40"
down_revision: str | Sequence[str] | None = "65f008584804"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_runs", sa.Column("current_step", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("research_runs", "current_step")
