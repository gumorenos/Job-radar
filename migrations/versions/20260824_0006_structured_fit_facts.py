"""Add structured candidate and job requirement facts.

Revision ID: 20260824_0006
Revises: 20260824_0005
Create Date: 2026-08-24
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0006"
down_revision: str | Sequence[str] | None = "20260824_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY_JSON_ARRAY = sa.text("'[]'::jsonb")


def upgrade() -> None:
    op.add_column(
        "candidate_profiles",
        sa.Column("experience_years", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "candidate_profiles",
        sa.Column(
            "degrees",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_EMPTY_JSON_ARRAY,
        ),
    )
    op.add_column(
        "candidate_profiles",
        sa.Column(
            "skills",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_EMPTY_JSON_ARRAY,
        ),
    )
    op.add_column(
        "candidate_profiles",
        sa.Column(
            "transferable_skills",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_EMPTY_JSON_ARRAY,
        ),
    )

    op.add_column(
        "jobs",
        sa.Column("required_experience_years", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "required_degrees",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_EMPTY_JSON_ARRAY,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "required_skills",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_EMPTY_JSON_ARRAY,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "required_skills")
    op.drop_column("jobs", "required_degrees")
    op.drop_column("jobs", "required_experience_years")
    op.drop_column("candidate_profiles", "transferable_skills")
    op.drop_column("candidate_profiles", "skills")
    op.drop_column("candidate_profiles", "degrees")
    op.drop_column("candidate_profiles", "experience_years")
