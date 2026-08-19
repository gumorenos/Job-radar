from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.models import DuplicateCandidate
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.worker.tasks import claim_next_task, execute_task


def _auth_headers() -> dict[str, str]:
    key = get_settings().api_key.get_secret_value()
    return {"Authorization": f"Bearer {key}"}


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
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


def _process_until_idle() -> None:
    for _ in range(20):
        with get_session_factory()() as session:
            claimed = claim_next_task(session, "confidential-duplicate-test")
        if claimed is None:
            return
        with get_session_factory()() as session:
            execute_task(session, claimed)
    raise AssertionError("Worker queue did not become idle.")


def _ingest(client: TestClient, key: str, title: str) -> None:
    response = client.post(
        "/api/v1/ingestions/jobs",
        headers={**_auth_headers(), "Idempotency-Key": key},
        json={
            "ingestion_source": "openclaw",
            "posting_source": "linkedin",
            "external_id": key,
            "job": {
                "title": title,
                "company": "Empresa Confidencial",
                "location": "Lima",
                "work_mode": "hybrid",
                "description": "People Analytics y gestión humana.",
                "url": f"https://example.com/jobs/{key}",
            },
        },
    )
    assert response.status_code == 202
    _process_until_idle()


def test_similar_confidential_jobs_are_not_assumed_same_company() -> None:
    with TestClient(app) as client:
        _ingest(client, "confidential-dup-1", "Senior People Analytics Analyst")
        _ingest(client, "confidential-dup-2", "People Analytics Senior Analyst")
        duplicate_list = client.get("/api/v1/radar/duplicates")

    assert duplicate_list.status_code == 200
    assert duplicate_list.json()["total"] == 0
    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(DuplicateCandidate)) == 0
