"""Add provenance-aware career evidence bank.

Revision ID: 20260901_0007
Revises: 20260824_0006
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0007"
down_revision: str | Sequence[str] | None = "20260824_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "career_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("generated_by_ai", sa.Boolean(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["candidate_profile_id"],
            ["candidate_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_career_evidence_profile_status",
        "career_evidence",
        ["candidate_profile_id", "verification_status"],
        unique=False,
    )
    op.create_index(
        "ix_career_evidence_profile_archived",
        "career_evidence",
        ["candidate_profile_id", "archived_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_career_evidence_profile_archived", table_name="career_evidence")
    op.drop_index("ix_career_evidence_profile_status", table_name="career_evidence")
    op.drop_table("career_evidence")
