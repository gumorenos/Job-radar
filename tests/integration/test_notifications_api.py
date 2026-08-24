from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.enums import (
    Classification,
    Confidence,
    JobStatus,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    WorkMode,
)
from app.db.models import CandidateProfile, Job, MatchAnalysis, Notification
from app.db.session import get_engine, get_session_factory
from app.main import app


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


def _seed_inbox() -> tuple[UUID, UUID]:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        profile = CandidateProfile(name="Perfil inbox")
        job = Job(
            canonical_title="Strategic HR Business Partner",
            title_key="strategic hr business partner",
            company_name_raw="Inbox Corp",
            company_is_confidential=False,
            description="HRBP y Gestión Humana",
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add_all([profile, job])
        session.flush()
        analysis = MatchAnalysis(
            job_id=job.id,
            candidate_profile_id=profile.id,
            overall_score=None,
            classification=Classification.HIGH_PRIORITY,
            confidence=Confidence.HIGH,
            rule_results={},
            skill_analysis={},
            strengths=[],
            gaps=[],
            recommendation="PRIORIZAR",
            explanation="Buen encaje para el perfil objetivo.",
            analyzer_version="rules-v4",
        )
        session.add(analysis)
        session.flush()
        first = Notification(
            job_id=job.id,
            match_analysis_id=analysis.id,
            channel=NotificationChannel.DASHBOARD,
            notification_type=NotificationType.IMMEDIATE,
            scheduled_for=now,
            sent_at=now,
            status=NotificationStatus.SENT,
        )
        second = Notification(
            job_id=job.id,
            match_analysis_id=analysis.id,
            channel=NotificationChannel.DASHBOARD,
            notification_type=NotificationType.IMMEDIATE,
            scheduled_for=now,
            sent_at=now,
            status=NotificationStatus.SENT,
        )
        telegram = Notification(
            job_id=job.id,
            match_analysis_id=analysis.id,
            channel=NotificationChannel.TELEGRAM,
            notification_type=NotificationType.IMMEDIATE,
            scheduled_for=now,
            status=NotificationStatus.PENDING,
        )
        session.add_all([first, second, telegram])
        session.commit()
        return first.id, telegram.id


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
    assert payload["items"][0]["read_at"] is None

    assert dashboard.status_code == 200
    assert dashboard.json()["total"] == 0


def test_dashboard_inbox_counts_only_dashboard_and_keeps_exact_total_with_limit() -> None:
    _seed_inbox()

    with TestClient(app) as client:
        summary = client.get("/api/v1/notifications/inbox/summary")
        inbox = client.get("/api/v1/notifications/inbox?limit=1")

    assert summary.status_code == 200
    assert summary.json() == {"total": 2, "unread": 2}

    assert inbox.status_code == 200
    payload = inbox.json()
    assert payload["total"] == 2
    assert payload["unread"] == 2
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["title"] == "Strategic HR Business Partner"
    assert item["company"] == "Inbox Corp"
    assert item["classification"] == "HIGH_PRIORITY"
    assert item["recommendation"] == "PRIORIZAR"
    assert item["read_at"] is None


def test_notification_lists_support_offset_with_exact_totals() -> None:
    _seed_inbox()

    with TestClient(app) as client:
        inbox_first = client.get("/api/v1/notifications/inbox?limit=1&offset=0")
        inbox_second = client.get("/api/v1/notifications/inbox?limit=1&offset=1")
        inbox_beyond = client.get("/api/v1/notifications/inbox?limit=1&offset=2")
        generic_first = client.get("/api/v1/notifications?channel=DASHBOARD&limit=1&offset=0")
        generic_second = client.get("/api/v1/notifications?channel=DASHBOARD&limit=1&offset=1")
        invalid_inbox = client.get("/api/v1/notifications/inbox?offset=-1")
        invalid_generic = client.get("/api/v1/notifications?offset=-1")

    assert inbox_first.status_code == 200
    assert inbox_second.status_code == 200
    assert inbox_beyond.status_code == 200
    assert inbox_first.json()["total"] == 2
    assert inbox_second.json()["total"] == 2
    assert inbox_beyond.json()["total"] == 2
    assert inbox_first.json()["items"][0]["id"] != inbox_second.json()["items"][0]["id"]
    assert inbox_beyond.json()["items"] == []

    assert generic_first.status_code == 200
    assert generic_second.status_code == 200
    assert generic_first.json()["total"] == 2
    assert generic_second.json()["total"] == 2
    assert generic_first.json()["items"][0]["id"] != generic_second.json()["items"][0]["id"]
    assert invalid_inbox.status_code == 422
    assert invalid_generic.status_code == 422


def test_mark_one_notification_read_is_idempotent_and_rejects_telegram() -> None:
    dashboard_id, telegram_id = _seed_inbox()

    with TestClient(app) as client:
        first = client.post(f"/api/v1/notifications/{dashboard_id}/read")
        replay = client.post(f"/api/v1/notifications/{dashboard_id}/read")
        telegram = client.post(f"/api/v1/notifications/{telegram_id}/read")
        summary = client.get("/api/v1/notifications/inbox/summary")
        unread = client.get("/api/v1/notifications/inbox?unread_only=true")

    assert first.status_code == 200
    assert first.json()["updated"] == 1
    assert first.json()["read_at"] is not None
    assert replay.status_code == 200
    assert replay.json()["updated"] == 0
    assert replay.json()["read_at"] == first.json()["read_at"]
    assert telegram.status_code == 404
    assert summary.json() == {"total": 2, "unread": 1}
    assert unread.json()["total"] == 2
    assert unread.json()["unread"] == 1
    assert len(unread.json()["items"]) == 1


def test_mark_all_notifications_read_only_affects_dashboard() -> None:
    _, telegram_id = _seed_inbox()

    with TestClient(app) as client:
        marked = client.post("/api/v1/notifications/inbox/read-all")
        summary = client.get("/api/v1/notifications/inbox/summary")
        unread = client.get("/api/v1/notifications/inbox?unread_only=true")
        telegram = client.get("/api/v1/notifications?channel=TELEGRAM")

    assert marked.status_code == 200
    assert marked.json()["updated"] == 2
    assert marked.json()["read_at"] is not None
    assert summary.json() == {"total": 2, "unread": 0}
    assert unread.json()["items"] == []
    assert telegram.json()["total"] == 1
    assert telegram.json()["items"][0]["id"] == str(telegram_id)
    assert telegram.json()["items"][0]["read_at"] is None
