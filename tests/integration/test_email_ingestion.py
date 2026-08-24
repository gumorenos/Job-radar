from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.enums import Classification, IngestionStatus, TaskStatus
from app.db.models import (
    EmailAttachment,
    EmailExtractedPosting,
    EmailProcessingRun,
    InboundEmail,
    IngestionEvent,
    Job,
    MatchAnalysis,
    ProcessingTask,
)
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


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _process_until_idle() -> None:
    for _ in range(20):
        with get_session_factory()() as session:
            claimed = claim_next_task(session, "email-ingestion-test-worker")
        if claimed is None:
            return
        with get_session_factory()() as session:
            execute_task(session, claimed)
    raise AssertionError("Worker queue did not become idle within 20 tasks.")


def _email_payload(subject: str = "Vacante People Analytics") -> dict[str, object]:
    return {
        "provider": "AgentMail",
        "provider_message_id": "provider-msg-001",
        "sender": "jobs@example.com",
        "recipients": ["radar@example.test"],
        "subject": subject,
        "text_body": "Senior People Analytics Analyst en Lima. S/ 9,000.",
        "provider_received_at": "2026-08-23T20:30:00-05:00",
        "attachments": [
            {
                "provider_attachment_id": "attachment-1",
                "filename": "job.txt",
                "content_type": "text/plain",
                "size_bytes": 120,
                "sha256": "a" * 64,
                "metadata": {"disposition": "attachment"},
            }
        ],
        "metadata": {"mailbox": "job-radar"},
    }


def test_inbound_email_is_authenticated_idempotent_and_preserves_raw_payload() -> None:
    payload = _email_payload()
    with TestClient(app) as client:
        unauthorized = client.post("/api/v1/emails/inbound", json=payload)
        first = client.post(
            "/api/v1/emails/inbound",
            headers={**_auth_headers(), "Idempotency-Key": "email-001"},
            json=payload,
        )
        replay = client.post(
            "/api/v1/emails/inbound",
            headers={**_auth_headers(), "Idempotency-Key": "email-001"},
            json=payload,
        )
        conflict = client.post(
            "/api/v1/emails/inbound",
            headers={**_auth_headers(), "Idempotency-Key": "email-001"},
            json=_email_payload("Vacante modificada"),
        )
        listing = client.get("/api/v1/emails/inbound?provider=AGENTMAIL&limit=1")

    assert unauthorized.status_code == 401
    assert first.status_code == 202
    assert first.json()["already_accepted"] is False
    assert first.json()["status"] == "RECEIVED"
    assert replay.status_code == 202
    assert replay.json()["already_accepted"] is True
    assert replay.json()["email_id"] == first.json()["email_id"]
    assert conflict.status_code == 409

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["provider"] == "agentmail"
    item = listing.json()["items"][0]
    assert item["attachment_count"] == 1
    assert "text_body" not in item
    assert "html_body" not in item

    with get_session_factory()() as session:
        assert _count(session, InboundEmail) == 1
        assert _count(session, EmailAttachment) == 1
        email = session.scalar(select(InboundEmail))
        attachment = session.scalar(select(EmailAttachment))
        assert email is not None
        assert attachment is not None
        assert email.provider == "agentmail"
        assert email.raw_payload["subject"] == "Vacante People Analytics"
        assert email.raw_payload["metadata"] == {"mailbox": "job-radar"}
        assert attachment.storage_path is None
        assert attachment.sha256 == "a" * 64


def test_provider_message_id_is_a_retry_identity_when_header_is_missing() -> None:
    payload = _email_payload()
    with TestClient(app) as client:
        first = client.post("/api/v1/emails/inbound", headers=_auth_headers(), json=payload)
        replay = client.post("/api/v1/emails/inbound", headers=_auth_headers(), json=payload)

    assert first.status_code == 202
    assert first.json()["already_accepted"] is False
    assert first.json()["idempotency_key"] == "message:provider-msg-001"
    assert replay.status_code == 202
    assert replay.json()["already_accepted"] is True
    assert replay.json()["email_id"] == first.json()["email_id"]

    with get_session_factory()() as session:
        assert _count(session, InboundEmail) == 1


def test_extraction_handoff_enters_normal_job_pipeline_and_retry_does_not_duplicate() -> None:
    posting: dict[str, object] = {
        "posting_source": "linkedin",
        "external_id": "email-linkedin-001",
        "job": {
            "title": "Senior People Analytics Analyst",
            "company": "Analytics Corp",
            "location": "Lima",
            "work_mode": "hybrid",
            "salary_text": "S/ 9,000",
            "description": "People Analytics y HR Analytics para Gestión Humana.",
            "url": "https://example.com/jobs/email-people-analytics",
        },
        "metadata": {"extraction_confidence": "high"},
        "raw": {"source_fragment": "job-card-1"},
    }
    extraction: dict[str, object] = {
        "extractor_version": "email-rules-v1",
        "postings": [posting],
        "metadata": {"extractor": "provider-neutral-test"},
    }

    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/emails/inbound",
            headers={**_auth_headers(), "Idempotency-Key": "email-handoff-001"},
            json=_email_payload(),
        )
        email_id = accepted.json()["email_id"]
        first = client.post(
            f"/api/v1/emails/inbound/{email_id}/extractions",
            headers={**_auth_headers(), "Idempotency-Key": "extract-001"},
            json=extraction,
        )
        replay = client.post(
            f"/api/v1/emails/inbound/{email_id}/extractions",
            headers={**_auth_headers(), "Idempotency-Key": "extract-001"},
            json=extraction,
        )
        changed_posting: dict[str, object] = {
            **posting,
            "external_id": "email-linkedin-changed",
        }
        changed: dict[str, object] = {
            **extraction,
            "postings": [changed_posting],
        }
        conflict = client.post(
            f"/api/v1/emails/inbound/{email_id}/extractions",
            headers={**_auth_headers(), "Idempotency-Key": "extract-001"},
            json=changed,
        )

    assert accepted.status_code == 202
    assert first.status_code == 202
    assert first.json()["status"] == "COMPLETED"
    assert first.json()["posting_count"] == 1
    assert len(first.json()["results"]) == 1
    assert first.json()["results"][0]["status"] == "COMPLETED"
    assert first.json()["results"][0]["ingestion_id"] is not None
    assert replay.status_code == 202
    assert replay.json()["processing_run_id"] == first.json()["processing_run_id"]
    assert replay.json()["results"] == first.json()["results"]
    assert conflict.status_code == 409

    with get_session_factory()() as session:
        assert _count(session, EmailProcessingRun) == 1
        assert _count(session, EmailExtractedPosting) == 1
        assert _count(session, IngestionEvent) == 1
        assert _count(session, ProcessingTask) == 1
        event = session.scalar(select(IngestionEvent))
        extracted = session.scalar(select(EmailExtractedPosting))
        email = session.scalar(select(InboundEmail))
        assert event is not None
        assert extracted is not None
        assert email is not None
        assert event.ingestion_source == "email"
        assert extracted.ingestion_event_id == event.id
        assert extracted.extraction_payload["external_id"] == "email-linkedin-001"
        assert email.status == IngestionStatus.COMPLETED
        assert email.processed_at is not None

    _process_until_idle()

    with get_session_factory()() as session:
        assert _count(session, Job) == 1
        assert _count(session, MatchAnalysis) == 1
        analysis = session.scalar(select(MatchAnalysis))
        tasks = list(session.scalars(select(ProcessingTask)))
        assert analysis is not None
        assert analysis.classification == Classification.HIGH_PRIORITY
        assert all(task.status == TaskStatus.COMPLETED for task in tasks)


def test_empty_extraction_marks_email_processed_without_job_ingestion() -> None:
    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/emails/inbound",
            headers={**_auth_headers(), "Idempotency-Key": "email-empty-001"},
            json=_email_payload(),
        )
        response = client.post(
            f"/api/v1/emails/inbound/{accepted.json()['email_id']}/extractions",
            headers={**_auth_headers(), "Idempotency-Key": "extract-empty-001"},
            json={"extractor_version": "email-rules-v1", "postings": []},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["posting_count"] == 0
    assert response.json()["results"] == []

    with get_session_factory()() as session:
        email = session.scalar(select(InboundEmail))
        assert email is not None
        assert email.status == IngestionStatus.COMPLETED
        assert email.processed_at is not None
        assert _count(session, IngestionEvent) == 0
        assert _count(session, Job) == 0
