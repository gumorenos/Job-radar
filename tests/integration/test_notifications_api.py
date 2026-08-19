from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.enums import (
    JobStatus,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    WorkMode,
)
from app.db.models import Job, Notification
from app.db.session import get_engine, get_session_factory
from app.main import app


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


def _seed_notification() -> None:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        job = Job(
            canonical_title="Senior People Analytics Analyst",
            title_key="senior people analytics analyst",
            company_name_raw="QA Notifications Corp",
            company_is_confidential=False,
            description="People Analytics",
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(job)
        session.flush()
        session.add(
            Notification(
                job_id=job.id,
                channel=NotificationChannel.TELEGRAM,
                notification_type=NotificationType.IMMEDIATE,
                scheduled_for=now,
                status=NotificationStatus.PENDING,
            )
        )
        session.commit()


def test_notification_summary_and_filters() -> None:
    _seed_notification()

    with TestClient(app) as client:
        summary = client.get("/api/v1/notifications/summary")
        pending = client.get(
            "/api/v1/notifications?status=PENDING&channel=TELEGRAM&notification_type=IMMEDIATE"
        )
        dashboard = client.get("/api/v1/notifications?channel=DASHBOARD")

    assert summary.status_code == 200
    assert summary.json() == {"pending": 1, "sent": 0, "failed": 0, "skipped": 0}

    assert pending.status_code == 200
    payload = pending.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "Senior People Analytics Analyst"
    assert payload["items"][0]["company"] == "QA Notifications Corp"
    assert payload["items"][0]["channel"] == "TELEGRAM"

    assert dashboard.status_code == 200
    assert dashboard.json()["total"] == 0
