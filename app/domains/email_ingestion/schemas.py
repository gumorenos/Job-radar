from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.enums import IngestionStatus
from app.domains.ingestion.schemas import IncomingJob


class EmailAttachmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_attachment_id: str | None = Field(default=None, max_length=300)
    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class InboundEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=80)
    provider_message_id: str | None = Field(default=None, max_length=300)
    sender: str | None = Field(default=None, max_length=320)
    recipients: list[str] = Field(default_factory=list, max_length=100)
    cc_recipients: list[str] = Field(default_factory=list, max_length=100)
    bcc_recipients: list[str] = Field(default_factory=list, max_length=100)
    subject: str | None = Field(default=None, max_length=2000)
    text_body: str | None = Field(default=None, max_length=2_000_000)
    html_body: str | None = Field(default=None, max_length=4_000_000)
    provider_received_at: datetime | None = None
    attachments: list[EmailAttachmentInput] = Field(default_factory=list, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_unique_provider_attachment_ids(self) -> InboundEmailRequest:
        ids = [
            item.provider_attachment_id
            for item in self.attachments
            if item.provider_attachment_id is not None
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("provider_attachment_id values must be unique within one email.")
        return self


class InboundEmailAcceptance(BaseModel):
    email_id: UUID
    status: IngestionStatus
    received_at: datetime
    idempotency_key: str
    already_accepted: bool


class ExtractedEmailPosting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    posting_source: str | None = Field(default=None, max_length=80)
    external_id: str | None = Field(default=None, max_length=300)
    captured_at: datetime | None = None
    job: IncomingJob
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_minimum_identity(self) -> ExtractedEmailPosting:
        if not any((self.external_id, self.job.url, self.job.title)):
            raise ValueError("At least one of external_id, job.url, or job.title is required.")
        return self


class EmailExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extractor_version: str = Field(min_length=1, max_length=120)
    postings: list[ExtractedEmailPosting] = Field(max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmailExtractionPostingResult(BaseModel):
    ordinal: int
    extracted_posting_id: UUID
    ingestion_id: UUID | None
    status: IngestionStatus
    error_code: str | None


class EmailExtractionResponse(BaseModel):
    processing_run_id: UUID
    inbound_email_id: UUID
    status: IngestionStatus
    posting_count: int
    started_at: datetime
    completed_at: datetime | None
    results: list[EmailExtractionPostingResult]


class InboundEmailListItem(BaseModel):
    id: UUID
    provider: str
    provider_message_id: str | None
    sender: str | None
    subject: str | None
    status: IngestionStatus
    attachment_count: int
    received_at: datetime
    provider_received_at: datetime | None
    processed_at: datetime | None


class InboundEmailList(BaseModel):
    items: list[InboundEmailListItem]
    total: int
    provider: str | None
