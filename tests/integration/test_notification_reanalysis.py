from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.enums import Classification, NotificationChannel, NotificationType
from app.db.models import MatchAnalysis, Notification
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.worker.tasks import claim_next_task, execute_task


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().api_key.get_secret_value()}"}


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


def _drain_worker() -> None:
    for _ in range(20):
        with get_session_factory()() as session:
            claimed = claim_next_task(session, "notification-reanalysis-test")
        if claimed is None:
            return
        with get_session_factory()() as session:
            execute_task(session, claimed)
    raise AssertionError("Worker queue did not become idle.")


def _ingest(client: TestClient, key: str, job: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/ingestions/jobs",
        headers={**_auth_headers(), "Idempotency-Key": key},
        json={
            "ingestion_source": "openclaw",
            "posting_source": "linkedin",
            "job": job,
        },
    )
    assert response.status_code == 202
    _drain_worker()


def _high_priority_job(**overrides: object) -> dict[str, object]:
    job: dict[str, object] = {
        "title": "Senior People Analytics Analyst",
        "company": "Notification Noise Corp",
        "location": "Lima",
        "work_mode": "hybrid",
        "salary_text": "S/ 9,000",
        "description": "People Analytics y HR Analytics para decisiones de gestión humana.",
        "url": "https://example.com/jobs/notification-noise",
    }
    job.update(overrides)
    return job


def test_material_rediscovery_with_same_classification_does_not_repeat_notifications() -> None:
    with TestClient(app) as client:
        _ingest(client, "notification-noise-1", _high_priority_job())
        _ingest(
            client,
            "notification-noise-2",
            _high_priority_job(
                description=(
                    "People Analytics y HR Analytics para decisiones de gestión humana. "
                    "Ahora incluye una responsabilidad adicional de reporting ejecutivo."
                )
            ),
        )

    with get_session_factory()() as session:
        analyses = list(session.scalars(select(MatchAnalysis).order_by(MatchAnalysis.created_at)))
        notifications = list(session.scalars(select(Notification).order_by(Notification.created_at)))

        assert len(analyses) == 2
        assert all(item.classification == Classification.HIGH_PRIORITY for item in analyses)
        assert len(notifications) == 2
        assert {item.match_analysis_id for item in notifications} == {analyses[0].id}
        assert {item.channel for item in notifications} == {
            NotificationChannel.DASHBOARD,
            NotificationChannel.TELEGRAM,
        }


def test_classification_transition_still_creates_new_notifications() -> None:
    with TestClient(app) as client:
        _ingest(client, "notification-transition-1", _high_priority_job())
        _ingest(
            client,
            "notification-transition-2",
            _high_priority_job(
                salary_text="USD 2,500 monthly",
                salary_min=2500,
                salary_max=2500,
                salary_currency="USD",
                salary_period="monthly",
            ),
        )

    with get_session_factory()() as session:
        analyses = list(session.scalars(select(MatchAnalysis).order_by(MatchAnalysis.created_at)))
        notifications = list(session.scalars(select(Notification).order_by(Notification.created_at)))

        assert len(analyses) == 2
        assert analyses[0].classification == Classification.HIGH_PRIORITY
        assert analyses[1].classification == Classification.REVIEW
        assert len(notifications) == 4

        latest_notifications = [
            item for item in notifications if item.match_analysis_id == analyses[1].id
        ]
        assert len(latest_notifications) == 2
        by_channel = {item.channel: item for item in latest_notifications}
        assert by_channel[NotificationChannel.DASHBOARD].notification_type == NotificationType.IMMEDIATE
        assert by_channel[NotificationChannel.TELEGRAM].notification_type == NotificationType.DAILY_REVIEW
