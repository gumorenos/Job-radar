from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.enums import IngestionStatus, TaskStatus
from app.db.models import IngestionEvent, ProcessingTask
from app.db.session import get_session
from app.domains.ingestion.schemas import JobIngestionRequest, JobIngestionResponse
from app.domains.ingestion.service import IdempotencyConflictError, accept_job_ingestion

router = APIRouter(prefix="/api/v1/ingestions", tags=["ingestion"])
SessionDep = Annotated[Session, Depends(get_session)]


class IngestionSourceSummary(BaseModel):
    ingestion_source: str
    total: int
    received: int
    processing: int
    completed: int
    partial: int
    failed: int
    duplicate_request: int
    last_received_at: datetime | None
    last_processed_at: datetime | None


class IngestionOverview(BaseModel):
    sources: list[IngestionSourceSummary]
    pending_tasks: int
    running_tasks: int
    failed_tasks: int


class RecentIngestionItem(BaseModel):
    id: UUID
    ingestion_source: str
    posting_source: str | None
    external_id: str | None
    status: IngestionStatus
    error_code: str | None
    retry_count: int
    received_at: datetime
    captured_at: datetime | None
    processed_at: datetime | None


class RecentIngestionList(BaseModel):
    items: list[RecentIngestionItem]
    total: int
    source: str | None


def _empty_status_counts() -> dict[IngestionStatus, int]:
    return {item: 0 for item in IngestionStatus}


@router.get("/summary", response_model=IngestionOverview)
def ingestion_summary(session: SessionDep) -> IngestionOverview:
    rows = session.execute(
        select(
            IngestionEvent.ingestion_source,
            IngestionEvent.status,
            func.count(IngestionEvent.id),
            func.max(IngestionEvent.received_at),
            func.max(IngestionEvent.processed_at),
        ).group_by(IngestionEvent.ingestion_source, IngestionEvent.status)
    ).all()

    by_source: dict[str, dict[str, object]] = {}
    for source, ingestion_status, count, last_received, last_processed in rows:
        current = by_source.setdefault(
            source,
            {
                "counts": _empty_status_counts(),
                "last_received_at": None,
                "last_processed_at": None,
            },
        )
        counts = current["counts"]
        if not isinstance(counts, dict):
            raise RuntimeError("Invalid ingestion summary accumulator.")
        counts[ingestion_status] = int(count)

        current_received = current["last_received_at"]
        if current_received is None or (
            last_received is not None and last_received > current_received
        ):
            current["last_received_at"] = last_received

        current_processed = current["last_processed_at"]
        if current_processed is None or (
            last_processed is not None and last_processed > current_processed
        ):
            current["last_processed_at"] = last_processed

    sources: list[IngestionSourceSummary] = []
    for source, values in by_source.items():
        counts = values["counts"]
        if not isinstance(counts, dict):
            raise RuntimeError("Invalid ingestion summary counts.")
        sources.append(
            IngestionSourceSummary(
                ingestion_source=source,
                total=sum(int(value) for value in counts.values()),
                received=int(counts[IngestionStatus.RECEIVED]),
                processing=int(counts[IngestionStatus.PROCESSING]),
                completed=int(counts[IngestionStatus.COMPLETED]),
                partial=int(counts[IngestionStatus.PARTIAL]),
                failed=int(counts[IngestionStatus.FAILED]),
                duplicate_request=int(counts[IngestionStatus.DUPLICATE_REQUEST]),
                last_received_at=values["last_received_at"],
                last_processed_at=values["last_processed_at"],
            )
        )
    sources.sort(
        key=lambda item: item.last_received_at or datetime.min.replace(tzinfo=None),
        reverse=True,
    )

    task_counts = {item: 0 for item in TaskStatus}
    for task_status, count in session.execute(
        select(ProcessingTask.status, func.count(ProcessingTask.id)).group_by(ProcessingTask.status)
    ):
        task_counts[task_status] = int(count)

    return IngestionOverview(
        sources=sources,
        pending_tasks=task_counts[TaskStatus.PENDING],
        running_tasks=task_counts[TaskStatus.RUNNING],
        failed_tasks=task_counts[TaskStatus.FAILED],
    )


@router.get("/recent", response_model=RecentIngestionList)
def recent_ingestions(
    session: SessionDep,
    source: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=25, ge=1, le=100),
) -> RecentIngestionList:
    query = select(IngestionEvent).order_by(IngestionEvent.received_at.desc())
    count_query = select(func.count(IngestionEvent.id))
    normalized_source = source.strip() if source and source.strip() else None
    if normalized_source is not None:
        query = query.where(IngestionEvent.ingestion_source == normalized_source)
        count_query = count_query.where(IngestionEvent.ingestion_source == normalized_source)

    events = list(session.scalars(query.limit(limit)))
    return RecentIngestionList(
        items=[
            RecentIngestionItem(
                id=event.id,
                ingestion_source=event.ingestion_source,
                posting_source=event.posting_source,
                external_id=event.external_id,
                status=event.status,
                error_code=event.error_code,
                retry_count=event.retry_count,
                received_at=event.received_at,
                captured_at=event.captured_at,
                processed_at=event.processed_at,
            )
            for event in events
        ],
        total=int(session.scalar(count_query) or 0),
        source=normalized_source,
    )


@router.post(
    "/jobs",
    response_model=JobIngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def ingest_job(
    request: Request,
    payload: JobIngestionRequest,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JobIngestionResponse:
    # Preserve the complete semantic JSON document received from the integration, including
    # fields that the current normalized request schema does not yet understand.
    raw_json: Any = await request.json()
    if not isinstance(raw_json, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The ingestion payload must be a JSON object.",
        )

    try:
        result = accept_job_ingestion(
            session,
            payload,
            idempotency_key,
            raw_payload=raw_json,
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return JobIngestionResponse(
        ingestion_id=result.ingestion_id,
        status=result.status,
        received_at=result.received_at,
    )
