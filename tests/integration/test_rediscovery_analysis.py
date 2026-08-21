from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.enums import Classification, TaskStatus, TaskType
from app.db.models import Job, JobPosting, MatchAnalysis, PostingSighting, ProcessingTask
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.worker.tasks import claim_next_task, execute_task


def _auth_headers() -> dict[str, str]:
    api_key = get_settings().api_key.get_secret_value()
    return {"Authorization": f"Bearer {api_key}"}


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
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


def _process_next() -> TaskType:
    with get_session_factory()() as session:
        claimed = claim_next_task(session, "rediscovery-test-worker")
    assert claimed is not None
    with get_session_factory()() as session:
        execute_task(session, claimed)
    return claimed.task_type


def _ingest(
    client: TestClient,
    key: str,
    external_id: str,
    *,
    salary: str,
    description: str,
) -> None:
    response = client.post(
        "/api/v1/ingestions/jobs",
        headers={**_auth_headers(), "Idempotency-Key": key},
        json={
            "ingestion_source": "openclaw",
            "posting_source": "linkedin",
            "external_id": external_id,
            "job": {
                "title": "HR Business Partner",
                "company": "Rediscovery Corp",
                "location": "Lima",
                "work_mode": "hybrid",
                "salary_text": salary,
                "description": description,
                "url": "https://example.com/jobs/rediscovery?utm_source=qa",
            },
        },
    )
    assert response.status_code == 202


def test_rediscovery_refreshes_material_data_without_duplicate_pending_analysis() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "rediscovery-1",
            "source-1",
            salary="S/ 8,500",
            description="Original description",
        )
        assert _process_next() == TaskType.NORMALIZE_INGESTION

        # A material update arrives before the first queued analysis runs. The pending analysis
        # is enough because it will read the latest committed posting state.
        _ingest(
            client,
            "rediscovery-2",
            "source-2",
            salary="S/ 6,500",
            description="Updated description",
        )
        assert _process_next() == TaskType.NORMALIZE_INGESTION

        with get_session_factory()() as session:
            posting = session.scalar(select(JobPosting))
            job = session.scalar(select(Job))
            analysis_tasks = list(
                session.scalars(
                    select(ProcessingTask).where(
                        ProcessingTask.task_type == TaskType.ANALYZE_MATCH
                    )
                )
            )
            assert posting is not None
            assert job is not None
            assert posting.salary_text == "S/ 6,500"
            assert posting.description_raw == "Updated description"
            assert job.description == "Updated description"
            assert len(analysis_tasks) == 1
            assert analysis_tasks[0].status == TaskStatus.PENDING
            assert session.scalar(select(func.count()).select_from(PostingSighting)) == 2

        assert _process_next() == TaskType.ANALYZE_MATCH

        with get_session_factory()() as session:
            analyses = list(session.scalars(select(MatchAnalysis)))
            assert len(analyses) == 1
            assert analyses[0].classification == Classification.DISCARD

        # An identical later sighting updates provenance/last_seen only; it must not create a
        # fresh immutable analysis (and therefore cannot create duplicate notification intents).
        _ingest(
            client,
            "rediscovery-3",
            "source-3",
            salary="S/ 6,500",
            description="Updated description",
        )
        assert _process_next() == TaskType.NORMALIZE_INGESTION

    with get_session_factory()() as session:
        analysis_tasks = list(
            session.scalars(
                select(ProcessingTask).where(ProcessingTask.task_type == TaskType.ANALYZE_MATCH)
            )
        )
        assert len(analysis_tasks) == 1
        assert analysis_tasks[0].status == TaskStatus.COMPLETED
        assert session.scalar(select(func.count()).select_from(MatchAnalysis)) == 1
        assert session.scalar(select(func.count()).select_from(PostingSighting)) == 3
