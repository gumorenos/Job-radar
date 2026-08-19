"""Add possible duplicate review workflow.

Revision ID: 20260818_0003
Revises: 20260814_0002
Create Date: 2026-08-18
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0003"
down_revision: str | Sequence[str] | None = "20260814_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "duplicate_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("resolved_survivor_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["job_a_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_b_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resolved_survivor_job_id"],
            ["jobs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_a_id", "job_b_id", name="uq_duplicate_candidates_pair"),
    )
    op.create_index(
        "ix_duplicate_candidates_status_created",
        "duplicate_candidates",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_duplicate_candidates_status_created",
        table_name="duplicate_candidates",
    )
    op.drop_table("duplicate_candidates")
