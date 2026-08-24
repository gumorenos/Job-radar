from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import TaskStatus, TaskType
from app.db.models import ProcessingTask
from app.domains.matching.service import enqueue_job_analysis


@dataclass(frozen=True)
class AnalysisQueueResult:
    task: ProcessingTask
    created: bool


@dataclass(frozen=True)
class AnalysisQueueBatchResult:
    tasks: tuple[ProcessingTask, ...]
    created: int
    reused_pending: int


def ensure_pending_job_analysis(session: Session, job_id: UUID) -> AnalysisQueueResult:
    """Ensure one pending follow-up analysis exists for the latest committed job/profile state.

    A pending task can be reused because it has not read state yet. A running task is not enough:
    it may already have read older state, so callers need one pending follow-up behind it.
    """

    pending = session.scalar(
        select(ProcessingTask)
        .where(
            ProcessingTask.task_type == TaskType.ANALYZE_MATCH,
            ProcessingTask.entity_type == "job",
            ProcessingTask.entity_id == job_id,
            ProcessingTask.status == TaskStatus.PENDING,
        )
        .order_by(ProcessingTask.created_at.asc())
        .limit(1)
    )
    if pending is not None:
        return AnalysisQueueResult(task=pending, created=False)
    return AnalysisQueueResult(task=enqueue_job_analysis(session, job_id), created=True)


def ensure_pending_job_analyses(
    session: Session,
    job_ids: list[UUID],
) -> AnalysisQueueBatchResult:
    unique_job_ids = list(dict.fromkeys(job_ids))
    if not unique_job_ids:
        return AnalysisQueueBatchResult(tasks=(), created=0, reused_pending=0)

    pending_by_job: dict[UUID, ProcessingTask] = {}
    pending_tasks = session.scalars(
        select(ProcessingTask)
        .where(
            ProcessingTask.task_type == TaskType.ANALYZE_MATCH,
            ProcessingTask.entity_type == "job",
            ProcessingTask.entity_id.in_(unique_job_ids),
            ProcessingTask.status == TaskStatus.PENDING,
        )
        .order_by(ProcessingTask.created_at.asc())
    )
    for task in pending_tasks:
        pending_by_job.setdefault(task.entity_id, task)

    tasks: list[ProcessingTask] = []
    created = 0
    reused = 0
    for job_id in unique_job_ids:
        pending = pending_by_job.get(job_id)
        if pending is not None:
            tasks.append(pending)
            reused += 1
            continue
        tasks.append(enqueue_job_analysis(session, job_id))
        created += 1

    return AnalysisQueueBatchResult(
        tasks=tuple(tasks),
        created=created,
        reused_pending=reused,
    )
