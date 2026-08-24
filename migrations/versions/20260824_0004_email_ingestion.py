"""Add provider-neutral inbound email ingestion foundation.

Revision ID: 20260824_0004
Revises: 20260818_0003
Create Date: 2026-08-24
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0004"
down_revision: str | Sequence[str] | None = "20260818_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbound_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_message_id", sa.String(length=300), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("sender", sa.String(length=320), nullable=True),
        sa.Column(
            "recipients",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "cc_recipients",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "bcc_recipients",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("html_body", sa.Text(), nullable=True),
        sa.Column("provider_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "idempotency_key",
            name="uq_inbound_emails_provider_idempotency",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_message_id",
            name="uq_inbound_emails_provider_message",
        ),
    )
    op.create_index(
        "ix_inbound_emails_status_received",
        "inbound_emails",
        ["status", "received_at"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_emails_provider_received",
        "inbound_emails",
        ["provider", "received_at"],
        unique=False,
    )

    op.create_table(
        "email_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inbound_email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_attachment_id", sa.String(length=300), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
            ["inbound_email_id"],
            ["inbound_emails.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "inbound_email_id",
            "provider_attachment_id",
            name="uq_email_attachments_provider_id",
        ),
    )
    op.create_index(
        "ix_email_attachments_email",
        "email_attachments",
        ["inbound_email_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "email_processing_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inbound_email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("posting_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
            ["inbound_email_id"],
            ["inbound_emails.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "inbound_email_id",
            "idempotency_key",
            name="uq_email_processing_runs_idempotency",
        ),
    )
    op.create_index(
        "ix_email_processing_runs_email_created",
        "email_processing_runs",
        ["inbound_email_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "email_extracted_postings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inbound_email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email_processing_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("posting_source", sa.String(length=80), nullable=True),
        sa.Column("external_id", sa.String(length=300), nullable=True),
        sa.Column(
            "extraction_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ingestion_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
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
            ["inbound_email_id"],
            ["inbound_emails.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["email_processing_run_id"],
            ["email_processing_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_event_id"],
            ["ingestion_events.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "email_processing_run_id",
            "ordinal",
            name="uq_email_extracted_postings_run_ordinal",
        ),
    )
    op.create_index(
        "ix_email_extracted_postings_email",
        "email_extracted_postings",
        ["inbound_email_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_email_extracted_postings_email", table_name="email_extracted_postings")
    op.drop_table("email_extracted_postings")
    op.drop_index("ix_email_processing_runs_email_created", table_name="email_processing_runs")
    op.drop_table("email_processing_runs")
    op.drop_index("ix_email_attachments_email", table_name="email_attachments")
    op.drop_table("email_attachments")
    op.drop_index("ix_inbound_emails_provider_received", table_name="inbound_emails")
    op.drop_index("ix_inbound_emails_status_received", table_name="inbound_emails")
    op.drop_table("inbound_emails")
