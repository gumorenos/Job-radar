from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.enums import Classification, IngestionStatus, JobStatus, WorkMode
from app.db.models import (
    CandidateProfile,
    IngestionEvent,
    Job,
    JobPosting,
    MatchAnalysis,
    PostingSighting,
)
from app.db.session import get_engine, get_session_factory
from app.main import app

AUTH = {"Authorization": "Bearer ci-only-test-key"}
EXT_AUTH = {"Authorization": "Bearer ci-only-extension-key"}


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text("TRUNCATE TABLE candidate_profiles, ingestion_events, jobs CASCADE")
        )


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None]:
    _truncate_database()
    yield
    _truncate_database()


def test_ingestion_result_requires_bearer_auth_and_returns_404_for_unknown_id() -> None:
    unknown = "00000000-0000-0000-0000-000000000001"
    with TestClient(app) as client:
        unauthenticated = client.get(f"/api/v1/ingestions/jobs/{unknown}/result")
        missing = client.get(
            f"/api/v1/ingestions/jobs/{unknown}/result",
            headers=AUTH,
        )

    assert unauthenticated.status_code == 401
    assert missing.status_code == 404


def test_received_ingestion_reports_pending_before_normalization() -> None:
    with get_session_factory()() as session:
        event = IngestionEvent(
            ingestion_source="chrome_extension",
            posting_source="linkedin",
            raw_payload={"job": {"title": "Senior HR Analyst"}},
            payload_hash="a" * 64,
            status=IngestionStatus.RECEIVED,
        )
        session.add(event)
        session.commit()
        event_id = event.id

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/ingestions/jobs/{event_id}/result",
            headers=AUTH,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ingestion_status"] == "RECEIVED"
    assert payload["analysis_status"] == "PENDING"
    assert payload["job_id"] is None
    assert payload["classification"] is None


def test_completed_ingestion_resolves_job_and_latest_analysis() -> None:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        profile = CandidateProfile(name="Extension QA")
        job = Job(
            canonical_title="Senior People Analytics Analyst",
            title_key="senior people analytics analyst",
            company_name_raw="Extension QA Corp",
            company_is_confidential=False,
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        event = IngestionEvent(
            ingestion_source="chrome_extension",
            posting_source="linkedin",
            raw_payload={"job": {"title": job.canonical_title}},
            payload_hash="b" * 64,
            status=IngestionStatus.COMPLETED,
            processed_at=now,
        )
        session.add_all([profile, job, event])
        session.flush()
        posting = JobPosting(
            job_id=job.id,
            posting_source="linkedin",
            source_external_id="123456",
            source_url_raw="https://www.linkedin.com/jobs/view/123456/",
            title_raw=job.canonical_title,
            company_raw=job.company_name_raw,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(posting)
        session.flush()
        session.add(
            PostingSighting(
                ingestion_event_id=event.id,
                job_posting_id=posting.id,
                seen_at=now,
            )
        )
        session.add(
            MatchAnalysis(
                job_id=job.id,
                candidate_profile_id=profile.id,
                classification=Classification.HIGH_PRIORITY,
                recommendation="PRIORIZAR",
                analyzer_version="rules-v6",
            )
        )
        session.commit()
        event_id = event.id
        job_id = job.id

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/ingestions/jobs/{event_id}/result",
            headers=AUTH,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ingestion_status"] == "COMPLETED"
    assert payload["analysis_status"] == "READY"
    assert payload["job_id"] == str(job_id)
    assert payload["title"] == "Senior People Analytics Analyst"
    assert payload["company"] == "Extension QA Corp"
    assert payload["classification"] == "HIGH_PRIORITY"
    assert payload["recommendation"] == "PRIORIZAR"
    assert payload["analyzer_version"] == "rules-v6"


def test_extension_status_accepts_only_extension_key() -> None:
    with TestClient(app) as client:
        missing = client.get("/api/v1/extension/status")
        general_key = client.get("/api/v1/extension/status", headers=AUTH)
        extension_key = client.get("/api/v1/extension/status", headers=EXT_AUTH)

    assert missing.status_code == 401
    assert general_key.status_code == 401
    assert extension_key.status_code == 200
    assert extension_key.json() == {"status": "ok", "scope": "chrome_extension"}


def test_extension_ingestion_requires_extension_key_and_chrome_source() -> None:
    payload = {
        "ingestion_source": "chrome_extension",
        "posting_source": "linkedin",
        "job": {
            "title": "Senior HR Analyst",
            "url": "https://www.linkedin.com/jobs/view/999001/",
        },
    }
    with TestClient(app) as client:
        general_key = client.post("/api/v1/extension/jobs", headers=AUTH, json=payload)
        wrong_source = client.post(
            "/api/v1/extension/jobs",
            headers=EXT_AUTH,
            json={**payload, "ingestion_source": "manual"},
        )
        accepted = client.post(
            "/api/v1/extension/jobs",
            headers={**EXT_AUTH, "Idempotency-Key": "extension-scope-test"},
            json=payload,
        )

    assert general_key.status_code == 401
    assert wrong_source.status_code == 422
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "accepted"


def test_extension_result_cannot_read_non_extension_ingestion() -> None:
    with get_session_factory()() as session:
        event = IngestionEvent(
            ingestion_source="agentmail",
            posting_source="linkedin",
            raw_payload={"job": {"title": "HR Business Partner"}},
            payload_hash="c" * 64,
            status=IngestionStatus.RECEIVED,
        )
        session.add(event)
        session.commit()
        event_id = event.id

    with TestClient(app) as client:
        hidden = client.get(
            f"/api/v1/extension/jobs/{event_id}/result",
            headers=EXT_AUTH,
        )
        general = client.get(
            f"/api/v1/ingestions/jobs/{event_id}/result",
            headers=AUTH,
        )

    assert hidden.status_code == 404
    assert general.status_code == 200
