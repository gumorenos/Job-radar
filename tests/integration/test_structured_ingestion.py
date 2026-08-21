from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.enums import Classification
from app.db.models import Job, JobPosting, MatchAnalysis
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
            claimed = claim_next_task(session, "structured-ingestion-test")
        if claimed is None:
            return
        with get_session_factory()() as session:
            execute_task(session, claimed)
    raise AssertionError("Worker queue did not become idle.")


def test_structured_remote_salary_is_persisted_and_used_by_matching() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingestions/jobs",
            headers={**_auth_headers(), "Idempotency-Key": "structured-remote-1"},
            json={
                "ingestion_source": "openclaw",
                "posting_source": "linkedin",
                "job": {
                    "title": "Senior People Analytics Analyst",
                    "company": "Structured Corp",
                    "location": "Remote LATAM",
                    "country": "United States",
                    "city": "Remote",
                    "work_mode": "remote",
                    "seniority": "Senior",
                    "salary_min": 7000,
                    "salary_max": 7500,
                    "currency": "pen",
                    "salary_period": "month",
                    "url": "https://example.com/jobs/structured-remote",
                },
            },
        )
        assert response.status_code == 202
        _process_until_idle()

    with get_session_factory()() as session:
        job = session.scalar(select(Job))
        posting = session.scalar(select(JobPosting))
        analysis = session.scalar(select(MatchAnalysis))
        assert job is not None
        assert posting is not None
        assert analysis is not None
        assert job.country == "United States"
        assert job.city == "Remote"
        assert job.seniority == "Senior"
        assert posting.salary_min == Decimal("7000")
        assert posting.salary_max == Decimal("7500")
        assert posting.currency == "PEN"
        assert posting.salary_period == "month"
        assert analysis.classification == Classification.DISCARD
        results = cast(list[dict[str, object]], analysis.rule_results["results"])
        salary_rule = next(item for item in results if item["code"] == "PUBLISHED_SALARY")
        assert salary_rule["severity"] == "HARD"
