from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.enums import JobStatus, WorkMode
from app.db.models import Job
from app.db.session import get_engine, get_session_factory
from app.main import app


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
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


def _create_job(index: int) -> Job:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        job = Job(
            canonical_title=f"People Analytics {index}",
            title_key=f"people analytics {index}",
            company_name_raw=f"Pagination Corp {index}",
            company_is_confidential=False,
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(job)
        session.commit()
        return job


def test_application_offset_returns_distinct_pages_with_exact_total() -> None:
    jobs = [_create_job(index) for index in range(3)]

    with TestClient(app) as client:
        for job in jobs:
            created = client.post(f"/api/v1/applications/jobs/{job.id}")
            assert created.status_code == 200

        first = client.get("/api/v1/applications?stage=TO_APPLY&limit=1&offset=0")
        second = client.get("/api/v1/applications?stage=TO_APPLY&limit=1&offset=1")
        beyond = client.get("/api/v1/applications?stage=TO_APPLY&limit=1&offset=3")

    assert first.status_code == 200
    assert second.status_code == 200
    assert beyond.status_code == 200
    assert first.json()["total"] == 3
    assert second.json()["total"] == 3
    assert beyond.json()["total"] == 3
    assert len(first.json()["items"]) == 1
    assert len(second.json()["items"]) == 1
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
    assert beyond.json()["items"] == []


def test_application_offset_rejects_negative_values() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/applications?offset=-1")

    assert response.status_code == 422
