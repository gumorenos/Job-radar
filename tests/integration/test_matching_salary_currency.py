from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.enums import Classification
from app.db.models import MatchAnalysis
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
    for _ in range(10):
        with get_session_factory()() as session:
            claimed = claim_next_task(session, "foreign-salary-test")
        if claimed is None:
            return
        with get_session_factory()() as session:
            execute_task(session, claimed)
    raise AssertionError("Worker queue did not become idle.")


def test_strong_remote_fit_with_unconverted_usd_salary_stays_review() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingestions/jobs",
            headers={**_auth_headers(), "Idempotency-Key": "usd-review-1"},
            json={
                "ingestion_source": "openclaw",
                "posting_source": "linkedin",
                "job": {
                    "title": "Senior People Analytics Analyst",
                    "company": "Remote USD Corp",
                    "location": "Remote LATAM",
                    "country": "Peru",
                    "work_mode": "remote",
                    "salary_text": "USD 1,000 monthly",
                    "description": "People Analytics y HR Analytics para gestión humana.",
                    "url": "https://example.com/jobs/remote-usd-review",
                },
            },
        )
        assert response.status_code == 202
        _process_until_idle()

    with get_session_factory()() as session:
        analysis = session.scalar(select(MatchAnalysis))
        assert analysis is not None
        assert analysis.classification == Classification.REVIEW
        assert analysis.rule_results["requires_review"] is True
        salary_rule = next(
            item
            for item in analysis.rule_results["results"]
            if item["code"] == "PUBLISHED_SALARY"
        )
        assert salary_rule["severity"] == "WARNING"
        assert "no está normalizado" in salary_rule["message"]
