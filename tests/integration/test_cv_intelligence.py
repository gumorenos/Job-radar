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
                    job_application_events,
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
            canonical_title="Senior People Analytics Analyst",
            title_key="senior people analytics analyst",
            company_name_raw="CV Intelligence QA",
            company_is_confidential=False,
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            description="People Analytics, Power BI y Workforce Planning.",
            required_skills=["Power BI", "Workforce Planning"],
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(job)
        session.commit()
        return job


def test_ai_tailored_version_keeps_job_context_and_requires_human_approval() -> None:
    job = _create_job()
    with TestClient(app) as client:
        parent = client.post(
            "/api/v1/cvs",
            json={
                "name": "CV People Analytics",
                "content_text": "People Analytics. Built HR dashboards.",
            },
        )
        child = client.post(
            "/api/v1/cvs",
            json={
                "name": "CV People Analytics",
                "parent_cv_id": parent.json()["id"],
                "tailored_for_job_id": str(job.id),
                "generated_by_ai": True,
                "content_text": (
                    "People Analytics. Built 12 Power BI dashboards. "
                    "Led workforce planning for HR leaders."
                ),
            },
        )
        blocked = client.post(f"/api/v1/cvs/{child.json()['id']}/activate")
        comparison = client.get(f"/api/v1/cvs/{child.json()['id']}/comparison")

    assert child.status_code == 201
    assert child.json()["approval_status"] == "DRAFT"
    assert child.json()["tailored_for_job_id"] == str(job.id)
    assert blocked.status_code == 409

    assert comparison.status_code == 200
    payload = comparison.json()
    assert payload["generated_by_ai"] is True
    assert payload["parent_cv_id"] == parent.json()["id"]
    assert payload["summary"]["current_word_count"] > 0
    assert payload["summary"]["quantified_statement_count"] == 1
    assert any(item["needs_human_verification"] for item in payload["changes"])
    assert payload["job_context"]["job_id"] == str(job.id)
    skills = {item["skill"]: item["present"] for item in payload["job_context"]["required_skills"]}
    assert skills == {"Power BI": True, "Workforce Planning": True}


def test_tailored_job_context_requires_parent_and_existing_job() -> None:
    job = _create_job()
    unknown = "00000000-0000-0000-0000-000000000001"
    with TestClient(app) as client:
        parent = client.post(
            "/api/v1/cvs",
            json={"name": "CV Base", "content_text": "Experiencia real."},
        )
        without_parent = client.post(
            "/api/v1/cvs",
            json={
                "name": "Tailored orphan",
                "tailored_for_job_id": str(job.id),
                "content_text": "Experiencia real.",
            },
        )
        missing_job = client.post(
            "/api/v1/cvs",
            json={
                "name": "Tailored missing job",
                "parent_cv_id": parent.json()["id"],
                "tailored_for_job_id": unknown,
                "content_text": "Experiencia real.",
            },
        )

    assert without_parent.status_code == 409
    assert missing_job.status_code == 404


def test_manual_version_comparison_does_not_label_new_text_as_ai_verified() -> None:
    with TestClient(app) as client:
        parent = client.post(
            "/api/v1/cvs",
            json={"name": "CV HRBP", "content_text": "Managed onboarding."},
        )
        child = client.post(
            "/api/v1/cvs",
            json={
                "name": "CV HRBP",
                "parent_cv_id": parent.json()["id"],
                "content_text": "Managed onboarding. Coordinated regional HR operations.",
            },
        )
        comparison = client.get(f"/api/v1/cvs/{child.json()['id']}/comparison")
        parent_comparison = client.get(f"/api/v1/cvs/{parent.json()['id']}/comparison")

    assert comparison.status_code == 200
    assert comparison.json()["generated_by_ai"] is False
    assert comparison.json()["changes"]
    assert all(
        item["needs_human_verification"] is False
        for item in comparison.json()["changes"]
    )
    assert parent_comparison.status_code == 409
