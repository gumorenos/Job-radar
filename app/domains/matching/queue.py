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
