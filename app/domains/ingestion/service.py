from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import IngestionStatus, TaskStatus, TaskType
from app.db.models import IngestionEvent, ProcessingTask
from app.domains.ingestion.schemas import JobIngestionRequest


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused with a different request payload."""


@dataclass(frozen=True)
class IngestionResult:
    ingestion_id: UUID
    status: str
    received_at: datetime


def _payload_hash(data: dict[str, object]) -> str:
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def accept_job_ingestion(
    session: Session,
    payload: JobIngestionRequest,
    idempotency_key: str | None,
    raw_payload: dict[str, object],
) -> IngestionResult:
    payload_hash = _payload_hash(raw_payload)

    if idempotency_key:
        existing = session.scalar(
            select(IngestionEvent).where(
                IngestionEvent.ingestion_source == payload.ingestion_source,
                IngestionEvent.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.payload_hash != payload_hash:
                raise IdempotencyConflictError(
                    "Idempotency key was already used with a different payload."
                )
            return IngestionResult(
                ingestion_id=existing.id,
                status="already_accepted",
                received_at=existing.received_at,
            )

    received_at = datetime.now(timezone.utc)
    ingestion = IngestionEvent(
        ingestion_source=payload.ingestion_source,
        posting_source=payload.posting_source,
        external_id=payload.external_id,
        idempotency_key=idempotency_key,
        received_at=received_at,
        captured_at=payload.captured_at,
        raw_payload=raw_payload,
        payload_hash=payload_hash,
        status=IngestionStatus.RECEIVED,
    )
    session.add(ingestion)
    session.flush()

    session.add(
        ProcessingTask(
            task_type=TaskType.NORMALIZE_INGESTION,
            entity_type="ingestion_event",
            entity_id=ingestion.id,
            status=TaskStatus.PENDING,
            priority=100,
        )
    )
    session.commit()

    return IngestionResult(
        ingestion_id=ingestion.id,
        status="accepted",
        received_at=ingestion.received_at,
    )
