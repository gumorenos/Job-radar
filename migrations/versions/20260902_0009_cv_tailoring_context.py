"""Associate CV versions with optional tailoring job context.

Revision ID: 20260902_0009
Revises: 20260902_0008
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0009"
down_revision: str | Sequence[str] | None = "20260902_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cv_versions",
        sa.Column("tailored_for_job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cv_versions_tailored_for_job",
        "cv_versions",
        "jobs",
        ["tailored_for_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_cv_versions_tailored_job",
        "cv_versions",
        ["tailored_for_job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cv_versions_tailored_job", table_name="cv_versions")
    op.drop_constraint(
        "fk_cv_versions_tailored_for_job",
        "cv_versions",
        type_="foreignkey",
    )
    op.drop_column("cv_versions", "tailored_for_job_id")
