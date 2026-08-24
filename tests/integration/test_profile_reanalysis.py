from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db.enums import JobStatus, TaskStatus, TaskType, WorkMode
from app.db.models import Job, ProcessingTask
from app.db.session import get_engine, get_session_factory
from app.main import app


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    email_extracted_postings,
                    email_processing_runs,
                    email_attachments,
                    inbound_emails,
                    duplicate_candidates,
                    job_applications,
                    classification_feedback,
                    notifications,
                    match_analyses,
                    posting_sightings,
                    job_postings,
                    processing_tasks,
                    ingestion_events,
                    jobs,
                    cv_versions,
                    companies,
                    candidate_profiles
                CASCADE
                """
            )
        )


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None]:
    _truncate_database()
    yield
    _truncate_database()


def _job(title: str, status: JobStatus) -> Job:
    now = datetime.now(UTC)
    return Job(
        canonical_title=title,
        title_key=title.lower(),
        company_name_raw="Reanalysis Corp",
        company_is_confidential=False,
        location_text="Lima",
        work_mode=WorkMode.HYBRID,
        status=status,
        first_seen_at=now,
        last_seen_at=now,
    )


def test_reanalysis_queues_only_active_and_unknown_jobs_and_is_idempotent_while_pending() -> None:
    with get_session_factory()() as session:
        jobs = [
            _job("Active HRBP", JobStatus.ACTIVE),
            _job("Unknown People Lead", JobStatus.UNKNOWN),
            _job("Closed HR Manager", JobStatus.CLOSED),
            _job("Expired HR Analyst", JobStatus.EXPIRED),
        ]
        session.add_all(jobs)
        session.commit()
        eligible_ids = {jobs[0].id, jobs[1].id}

    with TestClient(app) as client:
        first = client.post("/api/v1/profile/reanalyze")
        second = client.post("/api/v1/profile/reanalyze")

    assert first.status_code == 202
    assert first.json() == {
        "jobs_considered": 2,
        "enqueued": 2,
        "reused_pending": 0,
    }
    assert second.status_code == 202
    assert second.json() == {
        "jobs_considered": 2,
        "enqueued": 0,
        "reused_pending": 2,
    }

    with get_session_factory()() as session:
        tasks = list(
            session.scalars(
                select(ProcessingTask).where(
                    ProcessingTask.task_type == TaskType.ANALYZE_MATCH
                )
            )
        )
        assert len(tasks) == 2
        assert {task.entity_id for task in tasks} == eligible_ids
        assert all(task.status == TaskStatus.PENDING for task in tasks)


def test_reanalysis_adds_one_pending_follow_up_when_analysis_is_already_running() -> None:
    with get_session_factory()() as session:
        job = _job("Running HRBP", JobStatus.ACTIVE)
        session.add(job)
        session.flush()
        running = ProcessingTask(
            task_type=TaskType.ANALYZE_MATCH,
            entity_type="job",
            entity_id=job.id,
            status=TaskStatus.RUNNING,
            priority=200,
            started_at=datetime.now(UTC),
            locked_at=datetime.now(UTC),
            locked_by="already-running-worker",
        )
        session.add(running)
        session.commit()
        job_id = job.id

    with TestClient(app) as client:
        response = client.post("/api/v1/profile/reanalyze")

    assert response.status_code == 202
    assert response.json() == {
        "jobs_considered": 1,
        "enqueued": 1,
        "reused_pending": 0,
    }

    with get_session_factory()() as session:
        tasks = list(
            session.scalars(
                select(ProcessingTask)
                .where(
                    ProcessingTask.task_type == TaskType.ANALYZE_MATCH,
                    ProcessingTask.entity_id == job_id,
                )
                .order_by(ProcessingTask.created_at.asc())
            )
        )
        assert len(tasks) == 2
        assert [task.status for task in tasks] == [TaskStatus.RUNNING, TaskStatus.PENDING]


def test_reanalysis_with_no_jobs_returns_empty_queue_summary() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/profile/reanalyze")

    assert response.status_code == 202
    assert response.json() == {
        "jobs_considered": 0,
        "enqueued": 0,
        "reused_pending": 0,
    }
