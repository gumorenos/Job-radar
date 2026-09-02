"""Add next-action planning and application timeline.

Revision ID: 20260902_0008
Revises: 20260901_0007
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0008"
down_revision: str | Sequence[str] | None = "20260901_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_applications", sa.Column("next_action", sa.Text(), nullable=True))
    op.add_column(
        "job_applications",
        sa.Column("next_action_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "job_applications",
        sa.Column("follow_up_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "job_applications",
        sa.Column("last_follow_up_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_job_applications_next_action_due",
        "job_applications",
        ["next_action_due_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_applications_follow_up_due",
        "job_applications",
        ["follow_up_due_at"],
        unique=False,
    )
    op.create_table(
        "job_application_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_stage", sa.String(length=24), nullable=True),
        sa.Column("to_stage", sa.String(length=24), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            ["application_id"],
            ["job_applications.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_application_events_application_created",
        "job_application_events",
        ["application_id", "created_at"],
        unique=False,
    )

    op.execute(
        sa.text(
            "UPDATE job_applications "
            "SET next_action = CASE "
            "WHEN stage = 'TO_APPLY' THEN 'Preparar postulación' "
            "WHEN stage = 'APPLIED' THEN 'Enviar seguimiento' "
            "WHEN stage = 'INTERVIEW' THEN 'Preparar entrevista' "
            "WHEN stage = 'OFFER' THEN 'Evaluar oferta' "
            "ELSE NULL END "
            "WHERE next_action IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_application_events_application_created",
        table_name="job_application_events",
    )
    op.drop_table("job_application_events")
    op.drop_index("ix_job_applications_follow_up_due", table_name="job_applications")
    op.drop_index("ix_job_applications_next_action_due", table_name="job_applications")
    op.drop_column("job_applications", "last_follow_up_at")
    op.drop_column("job_applications", "follow_up_due_at")
    op.drop_column("job_applications", "next_action_due_at")
    op.drop_column("job_applications", "next_action")
