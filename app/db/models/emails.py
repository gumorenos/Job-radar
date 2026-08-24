from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import IngestionStatus
from app.db.models.mixins import TimestampMixin


class InboundEmail(TimestampMixin, Base):
    __tablename__ = "inbound_emails"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "idempotency_key",
            name="uq_inbound_emails_provider_idempotency",
        ),
        UniqueConstraint(
            "provider",
            "provider_message_id",
            name="uq_inbound_emails_provider_message",
        ),
        Index("ix_inbound_emails_status_received", "status", "received_at"),
        Index("ix_inbound_emails_provider_received", "provider", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(300))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sender: Mapped[str | None] = mapped_column(String(320))
    recipients: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    cc_recipients: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    bcc_recipients: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    subject: Mapped[str | None] = mapped_column(Text)
    text_body: Mapped[str | None] = mapped_column(Text)
    html_body: Mapped[str | None] = mapped_column(Text)
    provider_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, native_enum=False, length=32),
        nullable=False,
        default=IngestionStatus.RECEIVED,
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailAttachment(TimestampMixin, Base):
    __tablename__ = "email_attachments"
    __table_args__ = (
        UniqueConstraint(
            "inbound_email_id",
            "provider_attachment_id",
            name="uq_email_attachments_provider_id",
        ),
        Index("ix_email_attachments_email", "inbound_email_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    inbound_email_id: Mapped[UUID] = mapped_column(
        ForeignKey("inbound_emails.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_attachment_id: Mapped[str | None] = mapped_column(String(300))
    filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    storage_path: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )


class EmailProcessingRun(TimestampMixin, Base):
    __tablename__ = "email_processing_runs"
    __table_args__ = (
        UniqueConstraint(
            "inbound_email_id",
            "idempotency_key",
            name="uq_email_processing_runs_idempotency",
        ),
        Index("ix_email_processing_runs_email_created", "inbound_email_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    inbound_email_id: Mapped[UUID] = mapped_column(
        ForeignKey("inbound_emails.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, native_enum=False, length=32),
        nullable=False,
        default=IngestionStatus.PROCESSING,
    )
    posting_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )


class EmailExtractedPosting(TimestampMixin, Base):
    __tablename__ = "email_extracted_postings"
    __table_args__ = (
        UniqueConstraint(
            "email_processing_run_id",
            "ordinal",
            name="uq_email_extracted_postings_run_ordinal",
        ),
        Index("ix_email_extracted_postings_email", "inbound_email_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    inbound_email_id: Mapped[UUID] = mapped_column(
        ForeignKey("inbound_emails.id", ondelete="CASCADE"),
        nullable=False,
    )
    email_processing_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("email_processing_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    posting_source: Mapped[str | None] = mapped_column(String(80))
    external_id: Mapped[str | None] = mapped_column(String(300))
    extraction_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    ingestion_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingestion_events.id", ondelete="SET NULL")
    )
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, native_enum=False, length=32),
        nullable=False,
        default=IngestionStatus.RECEIVED,
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
