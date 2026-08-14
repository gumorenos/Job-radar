from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.enums import IngestionStatus, TaskStatus, TaskType
from app.db.models import IngestionEvent, JobPosting, ProcessingTask
from app.domains.ingestion.processor import normalize_ingestion_event
from app.domains.matching.service import analyze_job, enqueue_job_analysis


@dataclass(frozen=True)
class ClaimedTask:
    id: UUID
    task_type: TaskType
    entity_type: str
    entity_id: UUID
    attempt_count: int
    max_attempts: int


def recover_stale_tasks(session: Session, stale_after_seconds: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    stale_ids = list(
        session.scalars(
            select(ProcessingTask.id).where(
                ProcessingTask.status == TaskStatus.RUNNING,
                ProcessingTask.locked_at < cutoff,
            )
        )
    )
    if not stale_ids:
        session.rollback()
        return 0

    session.execute(
        update(ProcessingTask)
        .where(ProcessingTask.id.in_(stale_ids))
        .values(
            status=TaskStatus.PENDING,
            locked_at=None,
            locked_by=None,
            started_at=None,
            error_code="STALE_LOCK_RECOVERED",
            error_message="Worker lock expired before task completion.",
        )
    )
    session.commit()
    return len(stale_ids)


def claim_next_task(session: Session, worker_id: str) -> ClaimedTask | None:
    now = datetime.now(UTC)
    task = session.scalar(
        select(ProcessingTask)
        .where(
            ProcessingTask.status == TaskStatus.PENDING,
            ProcessingTask.scheduled_at <= now,
        )
        .order_by(ProcessingTask.priority.asc(), ProcessingTask.scheduled_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if task is None:
        session.rollback()
        return None

    task.status = TaskStatus.RUNNING
    task.attempt_count += 1
    task.started_at = now
    task.locked_at = now
    task.locked_by = worker_id
    task.error_code = None
    task.error_message = None
    session.commit()

    return ClaimedTask(
        id=task.id,
        task_type=task.task_type,
        entity_type=task.entity_type,
        entity_id=task.entity_id,
        attempt_count=task.attempt_count,
        max_attempts=task.max_attempts,
    )


def execute_task(session: Session, claimed: ClaimedTask) -> None:
    if claimed.task_type == TaskType.NORMALIZE_INGESTION:
        posting_id = normalize_ingestion_event(session, claimed.entity_id)
        posting = session.get(JobPosting, posting_id)
        if posting is None:
            raise LookupError(f"Job posting {posting_id} disappeared after normalization.")
        enqueue_job_analysis(session, posting.job_id)
    elif claimed.task_type == TaskType.ANALYZE_MATCH:
        analyze_job(session, claimed.entity_id)
    else:
        raise NotImplementedError(f"Unsupported task type: {claimed.task_type}")

    task = session.get(ProcessingTask, claimed.id)
    if task is None:
        raise LookupError(f"Processing task {claimed.id} disappeared during execution.")

    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(UTC)
    task.locked_at = None
    task.locked_by = None
    session.commit()


def fail_task(session: Session, claimed: ClaimedTask, exc: Exception) -> None:
    task = session.get(ProcessingTask, claimed.id)
    if task is None:
        return

    terminal = claimed.attempt_count >= claimed.max_attempts
    task.status = TaskStatus.FAILED if terminal else TaskStatus.PENDING
    task.locked_at = None
    task.locked_by = None
    task.error_code = type(exc).__name__[:100]
    task.error_message = str(exc)[:2000]

    if terminal:
        task.completed_at = datetime.now(UTC)
    else:
        task.started_at = None
        task.completed_at = None
        backoff_seconds = min(300, 2 ** max(1, claimed.attempt_count))
        task.scheduled_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)

    if terminal and claimed.entity_type == "ingestion_event":
        event = session.get(IngestionEvent, claimed.entity_id)
        if event is not None:
            event.status = IngestionStatus.FAILED
            event.error_code = task.error_code
            event.error_message = task.error_message

    session.commit()
