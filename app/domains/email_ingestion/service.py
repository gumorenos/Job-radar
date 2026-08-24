from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.enums import IngestionStatus
from app.db.models import (
    EmailAttachment,
    EmailExtractedPosting,
    EmailProcessingRun,
    InboundEmail,
)
from app.domains.email_ingestion.schemas import (
    EmailExtractionPostingResult,
    EmailExtractionRequest,
    EmailExtractionResponse,
    ExtractedEmailPosting,
    InboundEmailAcceptance,
    InboundEmailList,
    InboundEmailListItem,
    InboundEmailRequest,
)
from app.domains.ingestion.schemas import JobIngestionRequest
from app.domains.ingestion.service import IdempotencyConflictError, accept_job_ingestion


class EmailIdempotencyConflictError(ValueError):
    """Raised when an email idempotency key is reused for a different semantic payload."""


class EmailExtractionConflictError(ValueError):
    """Raised when an extraction run idempotency key is reused with different postings."""


@dataclass(frozen=True)
class _EmailIdentity:
    provider: str
    provider_message_id: str | None
    idempotency_key: str
    payload_hash: str


def _semantic_hash(data: dict[str, Any]) -> str:
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_addresses(values: list[str]) -> list[str]:
    return [cleaned for item in values if (cleaned := item.strip())]


def _email_identity(payload: InboundEmailRequest, idempotency_key: str | None) -> _EmailIdentity:
    provider = payload.provider.strip().lower()
    provider_message_id = _clean_optional(payload.provider_message_id)
    canonical = payload.model_dump(mode="json")
    canonical["provider"] = provider
    canonical["provider_message_id"] = provider_message_id
    payload_hash = _semantic_hash(canonical)

    supplied_key = _clean_optional(idempotency_key)
    if supplied_key is not None and len(supplied_key) > 200:
        raise ValueError("Idempotency-Key must be 200 characters or fewer.")
    resolved_key = supplied_key
    if resolved_key is None and provider_message_id is not None:
        resolved_key = f"message:{provider_message_id}"
    if resolved_key is None:
        resolved_key = f"payload:{payload_hash}"
    if len(resolved_key) > 200:
        resolved_key = f"sha256:{hashlib.sha256(resolved_key.encode()).hexdigest()}"

    return _EmailIdentity(
        provider=provider,
        provider_message_id=provider_message_id,
        idempotency_key=resolved_key,
        payload_hash=payload_hash,
    )


def _existing_email(
    session: Session,
    identity: _EmailIdentity,
) -> InboundEmail | None:
    existing = session.scalar(
        select(InboundEmail).where(
            InboundEmail.provider == identity.provider,
            InboundEmail.idempotency_key == identity.idempotency_key,
        )
    )
    if existing is None and identity.provider_message_id is not None:
        existing = session.scalar(
            select(InboundEmail).where(
                InboundEmail.provider == identity.provider,
                InboundEmail.provider_message_id == identity.provider_message_id,
            )
        )
    if existing is None:
        return None
    if existing.payload_hash != identity.payload_hash:
        raise EmailIdempotencyConflictError(
            "Email idempotency identity was already used with a different payload."
        )
    return existing


def accept_inbound_email(
    session: Session,
    payload: InboundEmailRequest,
    idempotency_key: str | None,
    *,
    raw_payload: dict[str, object],
) -> InboundEmailAcceptance:
    identity = _email_identity(payload, idempotency_key)
    existing = _existing_email(session, identity)
    if existing is not None:
        return InboundEmailAcceptance(
            email_id=existing.id,
            status=existing.status,
            received_at=existing.received_at,
            idempotency_key=existing.idempotency_key,
            already_accepted=True,
        )

    received_at = datetime.now(UTC)
    email = InboundEmail(
        provider=identity.provider,
        provider_message_id=identity.provider_message_id,
        idempotency_key=identity.idempotency_key,
        payload_hash=identity.payload_hash,
        sender=_clean_optional(payload.sender),
        recipients=_clean_addresses(payload.recipients),
        cc_recipients=_clean_addresses(payload.cc_recipients),
        bcc_recipients=_clean_addresses(payload.bcc_recipients),
        subject=_clean_optional(payload.subject),
        text_body=payload.text_body,
        html_body=payload.html_body,
        provider_received_at=payload.provider_received_at,
        received_at=received_at,
        raw_payload=raw_payload,
        metadata_json=dict(payload.metadata),
        status=IngestionStatus.RECEIVED,
    )
    session.add(email)
    try:
        session.flush()
        for item in payload.attachments:
            session.add(
                EmailAttachment(
                    inbound_email_id=email.id,
                    provider_attachment_id=_clean_optional(item.provider_attachment_id),
                    filename=_clean_optional(item.filename),
                    content_type=_clean_optional(item.content_type),
                    size_bytes=item.size_bytes,
                    sha256=item.sha256.lower() if item.sha256 is not None else None,
                    storage_path=None,
                    metadata_json=dict(item.metadata),
                )
            )
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _existing_email(session, identity)
        if existing is None:
            raise
        return InboundEmailAcceptance(
            email_id=existing.id,
            status=existing.status,
            received_at=existing.received_at,
            idempotency_key=existing.idempotency_key,
            already_accepted=True,
        )

    return InboundEmailAcceptance(
        email_id=email.id,
        status=email.status,
        received_at=email.received_at,
        idempotency_key=email.idempotency_key,
        already_accepted=False,
    )


def list_inbound_emails(
    session: Session,
    *,
    provider: str | None,
    limit: int,
) -> InboundEmailList:
    normalized_provider = provider.strip().lower() if provider and provider.strip() else None
    attachment_counts = (
        select(
            EmailAttachment.inbound_email_id.label("email_id"),
            func.count(EmailAttachment.id).label("attachment_count"),
        )
        .group_by(EmailAttachment.inbound_email_id)
        .subquery()
    )
    query = (
        select(
            InboundEmail,
            func.coalesce(attachment_counts.c.attachment_count, 0),
        )
        .outerjoin(attachment_counts, attachment_counts.c.email_id == InboundEmail.id)
        .order_by(InboundEmail.received_at.desc())
    )
    count_query = select(func.count(InboundEmail.id))
    if normalized_provider is not None:
        query = query.where(InboundEmail.provider == normalized_provider)
        count_query = count_query.where(InboundEmail.provider == normalized_provider)

    rows = session.execute(query.limit(limit)).all()
    return InboundEmailList(
        items=[
            InboundEmailListItem(
                id=email.id,
                provider=email.provider,
                provider_message_id=email.provider_message_id,
                sender=email.sender,
                subject=email.subject,
                status=email.status,
                attachment_count=int(attachment_count),
                received_at=email.received_at,
                provider_received_at=email.provider_received_at,
                processed_at=email.processed_at,
            )
            for email, attachment_count in rows
        ],
        total=int(session.scalar(count_query) or 0),
        provider=normalized_provider,
    )


def _run_key(payload_hash: str, idempotency_key: str | None) -> str:
    supplied_key = _clean_optional(idempotency_key)
    if supplied_key is not None and len(supplied_key) > 200:
        raise ValueError("Idempotency-Key must be 200 characters or fewer.")
    return supplied_key or f"payload:{payload_hash}"


def _existing_processing_run(
    session: Session,
    *,
    email_id: UUID,
    idempotency_key: str,
    payload_hash: str,
) -> EmailProcessingRun | None:
    run = session.scalar(
        select(EmailProcessingRun).where(
            EmailProcessingRun.inbound_email_id == email_id,
            EmailProcessingRun.idempotency_key == idempotency_key,
        )
    )
    if run is None:
        return None
    if run.payload_hash != payload_hash:
        raise EmailExtractionConflictError(
            "Extraction idempotency key was already used with different postings."
        )
    return run


def _job_request(
    email: InboundEmail,
    run: EmailProcessingRun,
    posting: ExtractedEmailPosting,
) -> JobIngestionRequest:
    metadata = dict(posting.metadata)
    metadata.update(
        {
            "inbound_email_id": str(email.id),
            "email_processing_run_id": str(run.id),
            "email_provider": email.provider,
            "email_provider_message_id": email.provider_message_id,
            "email_extractor_version": run.extractor_version,
        }
    )
    return JobIngestionRequest(
        ingestion_source="email",
        posting_source=posting.posting_source,
        external_id=posting.external_id,
        captured_at=posting.captured_at or email.provider_received_at or email.received_at,
        job=posting.job,
        metadata=metadata,
        raw=dict(posting.raw),
    )


def _extraction_response(session: Session, run: EmailProcessingRun) -> EmailExtractionResponse:
    rows = list(
        session.scalars(
            select(EmailExtractedPosting)
            .where(EmailExtractedPosting.email_processing_run_id == run.id)
            .order_by(EmailExtractedPosting.ordinal.asc())
        )
    )
    return EmailExtractionResponse(
        processing_run_id=run.id,
        inbound_email_id=run.inbound_email_id,
        status=run.status,
        posting_count=run.posting_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
        results=[
            EmailExtractionPostingResult(
                ordinal=row.ordinal,
                extracted_posting_id=row.id,
                ingestion_id=row.ingestion_event_id,
                status=row.status,
                error_code=row.error_code,
            )
            for row in rows
        ],
    )


def submit_email_extraction(
    session: Session,
    email_id: UUID,
    payload: EmailExtractionRequest,
    idempotency_key: str | None,
) -> EmailExtractionResponse:
    email = session.get(InboundEmail, email_id)
    if email is None:
        raise LookupError("Inbound email not found.")

    canonical = payload.model_dump(mode="json")
    payload_hash = _semantic_hash(canonical)
    resolved_key = _run_key(payload_hash, idempotency_key)
    run = _existing_processing_run(
        session,
        email_id=email.id,
        idempotency_key=resolved_key,
        payload_hash=payload_hash,
    )
    if run is None:
        run = EmailProcessingRun(
            inbound_email_id=email.id,
            idempotency_key=resolved_key,
            payload_hash=payload_hash,
            extractor_version=payload.extractor_version.strip(),
            status=IngestionStatus.PROCESSING,
            posting_count=len(payload.postings),
            started_at=datetime.now(UTC),
            metadata_json=dict(payload.metadata),
        )
        session.add(run)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            run = _existing_processing_run(
                session,
                email_id=email.id,
                idempotency_key=resolved_key,
                payload_hash=payload_hash,
            )
            if run is None:
                raise
    elif run.status == IngestionStatus.COMPLETED:
        return _extraction_response(session, run)

    existing_rows = {
        row.ordinal: row
        for row in session.scalars(
            select(EmailExtractedPosting).where(
                EmailExtractedPosting.email_processing_run_id == run.id
            )
        )
    }
    successful = 0
    for ordinal, posting in enumerate(payload.postings):
        row = existing_rows.get(ordinal)
        if (
            row is not None
            and row.status == IngestionStatus.COMPLETED
            and row.ingestion_event_id is not None
        ):
            successful += 1
            continue

        if row is None:
            row = EmailExtractedPosting(
                inbound_email_id=email.id,
                email_processing_run_id=run.id,
                ordinal=ordinal,
                posting_source=posting.posting_source,
                external_id=posting.external_id,
                extraction_payload=posting.model_dump(mode="json"),
                status=IngestionStatus.PROCESSING,
            )
            session.add(row)
            session.commit()
            existing_rows[ordinal] = row
        else:
            row.status = IngestionStatus.PROCESSING
            row.error_code = None
            session.commit()

        job_payload = _job_request(email, run, posting)
        ingestion_raw: dict[str, object] = job_payload.model_dump(mode="json")
        ingestion_key = f"email:{email.id}:{run.id}:{ordinal}"
        try:
            ingestion = accept_job_ingestion(
                session,
                job_payload,
                ingestion_key,
                raw_payload=ingestion_raw,
            )
        except IdempotencyConflictError:
            row = session.get(EmailExtractedPosting, row.id)
            if row is None:
                raise RuntimeError("Email extraction row disappeared during processing.")
            row.status = IngestionStatus.FAILED
            row.error_code = "INGESTION_IDEMPOTENCY_CONFLICT"
            session.commit()
            continue

        row = session.get(EmailExtractedPosting, row.id)
        if row is None:
            raise RuntimeError("Email extraction row disappeared during ingestion handoff.")
        row.ingestion_event_id = ingestion.ingestion_id
        row.status = IngestionStatus.COMPLETED
        row.error_code = None
        session.commit()
        successful += 1

    now = datetime.now(UTC)
    run = session.get(EmailProcessingRun, run.id)
    email = session.get(InboundEmail, email.id)
    if run is None or email is None:
        raise RuntimeError("Email processing state disappeared before completion.")
    final_status = (
        IngestionStatus.COMPLETED
        if successful == len(payload.postings)
        else IngestionStatus.PARTIAL
    )
    run.status = final_status
    run.posting_count = len(payload.postings)
    run.completed_at = now
    email.status = final_status
    email.processed_at = now
    email.error_code = None if final_status == IngestionStatus.COMPLETED else "PARTIAL_EXTRACTION"
    session.commit()
    session.refresh(run)
    return _extraction_response(session, run)
