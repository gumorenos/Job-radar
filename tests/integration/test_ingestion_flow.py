from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.enums import IngestionStatus, TaskStatus
from app.db.models import Company, IngestionEvent, Job, JobPosting, PostingSighting, ProcessingTask
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.worker.tasks import claim_next_task, execute_task

_API_KEY = "ci-only-test-key"
_AUTH_HEADERS = {"Authorization": f"Bearer {_API_KEY}"}


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


def _process_one_pending_task() -> None:
    with get_session_factory()() as session:
        claimed = claim_next_task(session, "integration-test-worker")
    assert claimed is not None

    with get_session_factory()() as session:
        execute_task(session, claimed)


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_ingestion_is_idempotent_and_deduplicates_by_normalized_url() -> None:
    payload = {
        "ingestion_source": "openclaw",
        "posting_source": "linkedin",
        "external_id": "qa-linkedin-001",
        "job": {
            "title": "HR Business Partner",
            "company": "QA Example Corp",
            "location": "Lima, Perú",
            "work_mode": "Híbrido",
            "salary_text": "S/ 8,500",
            "description": "Strategic HRBP role",
            "url": "https://example.com/jobs/123?utm_source=qa&trackingId=abc",
            "published_at": "2026-08-14",
        },
        "metadata": {"qa_test": True},
        "unexpected_future_field": {"must_be_preserved": True},
    }

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/ingestions/jobs",
            headers={**_AUTH_HEADERS, "Idempotency-Key": "qa-job-001"},
            json=payload,
        )
        assert first.status_code == 202
        assert first.json()["status"] == "accepted"

        _process_one_pending_task()

        with get_session_factory()() as session:
            assert _count(session, IngestionEvent) == 1
            assert _count(session, Job) == 1
            assert _count(session, JobPosting) == 1
            assert _count(session, PostingSighting) == 1

            event = session.scalar(select(IngestionEvent))
            posting = session.scalar(select(JobPosting))
            task = session.scalar(select(ProcessingTask))
            assert event is not None
            assert posting is not None
            assert task is not None
            assert event.status == IngestionStatus.COMPLETED
            assert task.status == TaskStatus.COMPLETED
            assert event.raw_payload["unexpected_future_field"] == {"must_be_preserved": True}
            assert posting.source_url_normalized == "https://example.com/jobs/123"

        replay = client.post(
            "/api/v1/ingestions/jobs",
            headers={**_AUTH_HEADERS, "Idempotency-Key": "qa-job-001"},
            json=payload,
        )
        assert replay.status_code == 202
        assert replay.json()["status"] == "already_accepted"

        with get_session_factory()() as session:
            assert _count(session, IngestionEvent) == 1
            assert _count(session, Job) == 1
            assert _count(session, JobPosting) == 1
            assert _count(session, PostingSighting) == 1

        changed_payload = {**payload, "job": {**payload["job"], "title": "Modified title"}}
        conflict = client.post(
            "/api/v1/ingestions/jobs",
            headers={**_AUTH_HEADERS, "Idempotency-Key": "qa-job-001"},
            json=changed_payload,
        )
        assert conflict.status_code == 409

        duplicate_payload = {
            **payload,
            "external_id": "qa-linkedin-002",
            "job": {
                **payload["job"],
                "url": "https://example.com/jobs/123?utm_source=second&utm_campaign=test",
            },
        }
        duplicate = client.post(
            "/api/v1/ingestions/jobs",
            headers={**_AUTH_HEADERS, "Idempotency-Key": "qa-job-002"},
            json=duplicate_payload,
        )
        assert duplicate.status_code == 202
        _process_one_pending_task()

    with get_session_factory()() as session:
        assert _count(session, IngestionEvent) == 2
        assert _count(session, Job) == 1
        assert _count(session, JobPosting) == 1
        assert _count(session, PostingSighting) == 2


def test_confidential_company_does_not_create_placeholder_company() -> None:
    payload = {
        "ingestion_source": "openclaw",
        "posting_source": "linkedin",
        "job": {
            "title": "People Analytics Lead",
            "company": "Empresa Confidencial",
            "location": "Lima",
            "url": "https://example.com/jobs/confidential-456",
        },
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingestions/jobs",
            headers={**_AUTH_HEADERS, "Idempotency-Key": "qa-job-confidential"},
            json=payload,
        )
        assert response.status_code == 202
        _process_one_pending_task()

    with get_session_factory()() as session:
        job = session.scalar(select(Job))
        assert job is not None
        assert job.company_id is None
        assert job.company_name_raw == "Empresa Confidencial"
        assert job.company_is_confidential is True
        assert _count(session, Company) == 0


def test_minimal_payload_is_accepted_and_invalid_payload_is_rejected() -> None:
    with TestClient(app) as client:
        minimal = client.post(
            "/api/v1/ingestions/jobs",
            headers={**_AUTH_HEADERS, "Idempotency-Key": "qa-job-minimal"},
            json={
                "ingestion_source": "openclaw",
                "posting_source": "email",
                "job": {"title": "Senior People Analytics Analyst"},
            },
        )
        assert minimal.status_code == 202
        _process_one_pending_task()

        invalid = client.post(
            "/api/v1/ingestions/jobs",
            headers=_AUTH_HEADERS,
            json={"ingestion_source": "openclaw", "job": {}},
        )
        assert invalid.status_code == 422

    with get_session_factory()() as session:
        assert _count(session, Job) == 1
        job = session.scalar(select(Job))
        assert job is not None
        assert job.canonical_title == "Senior People Analytics Analyst"
