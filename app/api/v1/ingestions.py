from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.enums import IngestionStatus, TaskStatus, TaskType
from app.db.models import (
    IngestionEvent,
    Job,
    JobPosting,
    MatchAnalysis,
    PostingSighting,
    ProcessingTask,
)
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


class IngestionJobResult(BaseModel):
    ingestion_id: UUID
    ingestion_status: IngestionStatus
    analysis_status: str
    job_id: UUID | None
    title: str | None
    company: str | None
    classification: str | None
    recommendation: str | None
    analyzer_version: str | None
    error_code: str | None


@dataclass
class _SourceAccumulator:
    counts: dict[IngestionStatus, int]
    last_received_at: datetime | None = None
    last_processed_at: datetime | None = None


def _empty_status_counts() -> dict[IngestionStatus, int]:
    return {item: 0 for item in IngestionStatus}


def _job_for_ingestion(session: Session, ingestion_id: UUID) -> Job | None:
    sighting = session.scalar(
        select(PostingSighting)
        .where(PostingSighting.ingestion_event_id == ingestion_id)
        .order_by(PostingSighting.seen_at.desc())
        .limit(1)
    )
    if sighting is None:
        return None
    posting = session.get(JobPosting, sighting.job_posting_id)
    if posting is None:
        return None
    return session.get(Job, posting.job_id)


def _analysis_state(
    session: Session,
    job: Job,
) -> tuple[str, MatchAnalysis | None]:
    latest_task = session.scalar(
        select(ProcessingTask)
        .where(
            ProcessingTask.task_type == TaskType.ANALYZE_MATCH,
            ProcessingTask.entity_type == "job",
            ProcessingTask.entity_id == job.id,
        )
        .order_by(ProcessingTask.scheduled_at.desc(), ProcessingTask.id.desc())
        .limit(1)
    )
    latest_analysis = session.scalar(
        select(MatchAnalysis)
        .where(MatchAnalysis.job_id == job.id)
        .order_by(MatchAnalysis.created_at.desc())
        .limit(1)
    )
    if latest_task is not None and latest_task.status in {
        TaskStatus.PENDING,
        TaskStatus.RUNNING,
    }:
        return "PENDING", None
    if latest_task is not None and latest_task.status == TaskStatus.FAILED:
        return "FAILED", None
    if latest_analysis is not None:
        return "READY", latest_analysis
    return "UNAVAILABLE", None


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

    by_source: dict[str, _SourceAccumulator] = {}
    for source, ingestion_status, count, last_received, last_processed in rows:
        current = by_source.setdefault(source, _SourceAccumulator(counts=_empty_status_counts()))
        current.counts[ingestion_status] = int(count)
        if current.last_received_at is None or (
            last_received is not None and last_received > current.last_received_at
        ):
            current.last_received_at = last_received
        if current.last_processed_at is None or (
            last_processed is not None and last_processed > current.last_processed_at
        ):
            current.last_processed_at = last_processed

    sources = [
        IngestionSourceSummary(
            ingestion_source=source,
            total=sum(values.counts.values()),
            received=values.counts[IngestionStatus.RECEIVED],
            processing=values.counts[IngestionStatus.PROCESSING],
            completed=values.counts[IngestionStatus.COMPLETED],
            partial=values.counts[IngestionStatus.PARTIAL],
            failed=values.counts[IngestionStatus.FAILED],
            duplicate_request=values.counts[IngestionStatus.DUPLICATE_REQUEST],
            last_received_at=values.last_received_at,
            last_processed_at=values.last_processed_at,
        )
        for source, values in by_source.items()
    ]
    sources.sort(
        key=lambda item: item.last_received_at or datetime.min.replace(tzinfo=UTC),
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


@router.get(
    "/jobs/{ingestion_id}/result",
    response_model=IngestionJobResult,
    dependencies=[Depends(require_api_key)],
)
def ingestion_job_result(ingestion_id: UUID, session: SessionDep) -> IngestionJobResult:
    event = session.get(IngestionEvent, ingestion_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Ingestion event not found.")

    job = _job_for_ingestion(session, ingestion_id)
    analysis_status = "UNAVAILABLE"
    analysis = None
    if job is not None:
        analysis_status, analysis = _analysis_state(session, job)
    elif event.status in {IngestionStatus.RECEIVED, IngestionStatus.PROCESSING}:
        analysis_status = "PENDING"
    elif event.status == IngestionStatus.FAILED:
        analysis_status = "FAILED"

    classification = None
    if analysis is not None and analysis.classification is not None:
        classification = analysis.classification.value

    return IngestionJobResult(
        ingestion_id=event.id,
        ingestion_status=event.status,
        analysis_status=analysis_status,
        job_id=job.id if job is not None else None,
        title=job.canonical_title if job is not None else None,
        company=job.company_name_raw if job is not None else None,
        classification=classification,
        recommendation=analysis.recommendation if analysis is not None else None,
        analyzer_version=analysis.analyzer_version if analysis is not None else None,
        error_code=event.error_code,
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
