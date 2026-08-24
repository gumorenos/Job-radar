from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.enums import IngestionStatus, TaskStatus, TaskType
from app.db.models import IngestionEvent, ProcessingTask
from app.db.session import get_engine, get_session_factory
from app.main import app


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    job_applications,
                    duplicate_candidates,
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


def test_ingestion_summary_groups_sources_and_queue_health_without_raw_payload() -> None:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        session.add_all(
            [
                IngestionEvent(
                    ingestion_source="openclaw",
                    posting_source="linkedin",
                    idempotency_key="obs-1",
                    raw_payload={"secret_like_raw": "must-not-leak"},
                    payload_hash="1" * 64,
                    status=IngestionStatus.COMPLETED,
                    received_at=now - timedelta(minutes=5),
                    processed_at=now - timedelta(minutes=4),
                ),
                IngestionEvent(
                    ingestion_source="openclaw",
                    posting_source="jobsora",
                    idempotency_key="obs-2",
                    raw_payload={"title": "Second"},
                    payload_hash="2" * 64,
                    status=IngestionStatus.FAILED,
                    error_code="NORMALIZE_FAILED",
                    received_at=now,
                ),
                IngestionEvent(
                    ingestion_source="manual",
                    idempotency_key="obs-3",
                    raw_payload={"title": "Manual"},
                    payload_hash="3" * 64,
                    status=IngestionStatus.RECEIVED,
                    received_at=now - timedelta(minutes=10),
                ),
                ProcessingTask(
                    task_type=TaskType.NORMALIZE_INGESTION,
                    entity_type="ingestion",
                    entity_id=uuid4(),
                    status=TaskStatus.PENDING,
                ),
                ProcessingTask(
                    task_type=TaskType.ANALYZE_MATCH,
                    entity_type="job",
                    entity_id=uuid4(),
                    status=TaskStatus.FAILED,
                ),
            ]
        )
        session.commit()

    with TestClient(app) as client:
        summary = client.get("/api/v1/ingestions/summary")
        recent = client.get("/api/v1/ingestions/recent?source=openclaw&limit=1")

    assert summary.status_code == 200
    payload = summary.json()
    openclaw = next(item for item in payload["sources"] if item["ingestion_source"] == "openclaw")
    assert openclaw["total"] == 2
    assert openclaw["completed"] == 1
    assert openclaw["failed"] == 1
    assert payload["pending_tasks"] == 1
    assert payload["failed_tasks"] == 1

    assert recent.status_code == 200
    recent_payload = recent.json()
    assert recent_payload["total"] == 2
    assert len(recent_payload["items"]) == 1
    assert recent_payload["items"][0]["status"] == "FAILED"
    assert recent_payload["items"][0]["error_code"] == "NORMALIZE_FAILED"
    assert "raw_payload" not in recent_payload["items"][0]
    assert "secret_like_raw" not in recent.text
