"""Initial Job Radar PostgreSQL schema.

Revision ID: 20260814_0001
Revises:
Create Date: 2026-08-14
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "candidate_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("salary_min_pen", sa.Numeric(12, 2), nullable=False),
        sa.Column("remote_salary_multiplier", sa.Numeric(5, 2), nullable=False),
        sa.Column("target_locations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("target_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("target_areas", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("adjacent_areas", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("daily_review_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("linkedin_url", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(length=200), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("is_confidential_placeholder", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name", name="uq_companies_normalized_name"),
    )

    op.create_table(
        "ingestion_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingestion_source", sa.String(length=80), nullable=False),
        sa.Column("posting_source", sa.String(length=80), nullable=True),
        sa.Column("external_id", sa.String(length=300), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingestion_source",
            "idempotency_key",
            name="uq_ingestion_events_source_idempotency",
        ),
    )
    op.create_index(
        "ix_ingestion_events_status_received",
        "ingestion_events",
        ["status", "received_at"],
        unique=False,
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_title", sa.String(length=300), nullable=True),
        sa.Column("title_key", sa.String(length=300), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_name_raw", sa.String(length=255), nullable=True),
        sa.Column("company_is_confidential", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location_text", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("work_mode", sa.String(length=16), nullable=False),
        sa.Column("employment_type", sa.String(length=120), nullable=True),
        sa.Column("seniority", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_status_last_seen", "jobs", ["status", "last_seen_at"], unique=False)
    op.create_index("ix_jobs_company_title_key", "jobs", ["company_id", "title_key"], unique=False)

    op.create_table(
        "cv_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_cv_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_base", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("approval_status", sa.String(length=24), nullable=False),
        sa.Column("generated_by_ai", sa.Boolean(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_role", sa.String(length=200), nullable=True),
        sa.Column("target_area", sa.String(length=200), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["candidate_profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["parent_cv_id"], ["cv_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_profile_id",
            "slug",
            "version",
            name="uq_cv_versions_profile_slug_version",
        ),
    )

    op.create_table(
        "job_postings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("posting_source", sa.String(length=80), nullable=True),
        sa.Column("source_external_id", sa.String(length=300), nullable=True),
        sa.Column("source_url_raw", sa.Text(), nullable=True),
        sa.Column("source_url_normalized", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("title_raw", sa.String(length=300), nullable=True),
        sa.Column("company_raw", sa.String(length=255), nullable=True),
        sa.Column("location_raw", sa.String(length=255), nullable=True),
        sa.Column("description_raw", sa.Text(), nullable=True),
        sa.Column("salary_text", sa.String(length=500), nullable=True),
        sa.Column("salary_min", sa.Numeric(14, 2), nullable=True),
        sa.Column("salary_max", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("salary_period", sa.String(length=40), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posting_status", sa.String(length=16), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "posting_source",
            "source_external_id",
            name="uq_job_postings_source_external_id",
        ),
    )
    op.create_index(
        "ix_job_postings_normalized_url", "job_postings", ["source_url_normalized"], unique=False
    )
    op.create_index(
        "ix_job_postings_job_status", "job_postings", ["job_id", "posting_status"], unique=False
    )

    op.create_table(
        "posting_sightings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingestion_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_posting_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["ingestion_event_id"], ["ingestion_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["job_posting_id"], ["job_postings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingestion_event_id",
            "job_posting_id",
            name="uq_posting_sightings_event_posting",
        ),
    )
    op.create_index(
        "ix_posting_sightings_posting_seen",
        "posting_sightings",
        ["job_posting_id", "seen_at"],
        unique=False,
    )

    op.create_table(
        "processing_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=200), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_tasks_status_schedule",
        "processing_tasks",
        ["status", "scheduled_at", "priority"],
        unique=False,
    )
    op.create_index(
        "ix_processing_tasks_entity", "processing_tasks", ["entity_type", "entity_id"], unique=False
    )

    op.create_table(
        "match_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cv_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("classification", sa.String(length=24), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("rule_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("skill_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gaps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("career_move_assessment", sa.Text(), nullable=True),
        sa.Column("salary_assessment", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.String(length=120), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("analyzer_version", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["cv_version_id"], ["cv_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_match_analyses_job_created", "match_analyses", ["job_id", "created_at"], unique=False
    )

    op.create_table(
        "classification_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("system_classification", sa.String(length=24), nullable=False),
        sa.Column("human_classification", sa.String(length=24), nullable=False),
        sa.Column("reason_code", sa.String(length=24), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["match_analysis_id"], ["match_analyses.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_classification_feedback_job_created",
        "classification_feedback",
        ["job_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("notification_type", sa.String(length=24), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["match_analysis_id"], ["match_analyses.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_status_scheduled",
        "notifications",
        ["status", "scheduled_for"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("classification_feedback")
    op.drop_table("match_analyses")
    op.drop_table("processing_tasks")
    op.drop_table("posting_sightings")
    op.drop_table("job_postings")
    op.drop_table("cv_versions")
    op.drop_table("jobs")
    op.drop_table("ingestion_events")
    op.drop_table("companies")
    op.drop_table("candidate_profiles")
