from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db.enums import ApplicationStage, JobStatus, WorkMode
from app.db.models import Job, JobApplication
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


def _create_job() -> Job:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        job = Job(
            canonical_title="Strategic HR Business Partner",
            title_key="strategic hr business partner",
            company_name_raw="CRM QA Corp",
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


def test_existing_job_without_application_returns_null() -> None:
    job = _create_job()

    with TestClient(app) as client:
        response = client.get(f"/api/v1/applications/by-job/{job.id}")

    assert response.status_code == 200
    assert response.json() is None


def test_add_job_is_idempotent_and_visible_in_to_apply() -> None:
    job = _create_job()

    with TestClient(app) as client:
        first = client.post(f"/api/v1/applications/jobs/{job.id}")
        second = client.post(f"/api/v1/applications/jobs/{job.id}")
        summary = client.get("/api/v1/applications/summary")
        listing = client.get("/api/v1/applications?stage=TO_APPLY")
        by_job = client.get(f"/api/v1/applications/by-job/{job.id}")

    assert first.status_code == 200
    assert first.json()["created"] is True
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert first.json()["application"]["id"] == second.json()["application"]["id"]
    assert summary.json() == {
        "to_apply": 1,
        "applied": 0,
        "interview": 0,
        "offer": 0,
        "closed": 0,
    }
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["title"] == "Strategic HR Business Partner"
    assert listing.json()["items"][0]["company"] == "CRM QA Corp"
    assert by_job.json()["stage"] == "TO_APPLY"

    with get_session_factory()() as session:
        rows = list(session.scalars(select(JobApplication)))
        assert len(rows) == 1


def test_application_stage_changes_and_preserves_application_timestamp() -> None:
    job = _create_job()

    with TestClient(app) as client:
        created = client.post(f"/api/v1/applications/jobs/{job.id}").json()["application"]
        application_id = created["id"]
        applied = client.patch(
            f"/api/v1/applications/{application_id}",
            json={"stage": "APPLIED", "notes": "  Postulación enviada por LinkedIn.  "},
        )
        interview = client.patch(
            f"/api/v1/applications/{application_id}", json={"stage": "INTERVIEW"}
        )
        closed = client.patch(
            f"/api/v1/applications/{application_id}", json={"stage": "CLOSED"}
        )
        reopened = client.patch(
            f"/api/v1/applications/{application_id}", json={"stage": "INTERVIEW"}
        )

    assert applied.status_code == 200
    assert applied.json()["stage"] == "APPLIED"
    assert applied.json()["notes"] == "Postulación enviada por LinkedIn."
    assert applied.json()["applied_at"] is not None
    applied_at = applied.json()["applied_at"]

    assert interview.json()["stage"] == "INTERVIEW"
    assert interview.json()["applied_at"] == applied_at
    assert closed.json()["stage"] == "CLOSED"
    assert closed.json()["closed_at"] is not None
    assert reopened.json()["stage"] == "INTERVIEW"
    assert reopened.json()["closed_at"] is None
    assert reopened.json()["applied_at"] == applied_at


def test_application_endpoints_return_404_for_unknown_entities() -> None:
    unknown = "00000000-0000-0000-0000-000000000001"
    with TestClient(app) as client:
        create = client.post(f"/api/v1/applications/jobs/{unknown}")
        get_by_job = client.get(f"/api/v1/applications/by-job/{unknown}")
        update = client.patch(
            f"/api/v1/applications/{unknown}", json={"stage": ApplicationStage.APPLIED}
        )

    assert create.status_code == 404
    assert get_by_job.status_code == 404
    assert update.status_code == 404
