from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.enums import (
    Classification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    TaskStatus,
    TaskType,
)
from app.db.models import CandidateProfile, MatchAnalysis, Notification, ProcessingTask
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
            claimed = claim_next_task(session, "matching-pipeline-test")
        if claimed is None:
            return
        with get_session_factory()() as session:
            execute_task(session, claimed)
    raise AssertionError("Worker queue did not become idle within 10 tasks.")


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
    _process_until_idle()


def test_worker_discards_excluded_seniority_and_radar_reflects_it() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "matching-junior",
            {
                "title": "Analista Junior de Recursos Humanos",
                "company": "Example Corp",
                "location": "Lima",
                "work_mode": "hybrid",
                "salary_text": "S/ 9,000",
                "url": "https://example.com/jobs/junior-hr",
            },
        )

        summary = client.get("/api/v1/radar/summary")
        discarded = client.get("/api/v1/radar/jobs?view=discarded")

    assert summary.status_code == 200
    assert summary.json()["discarded"] == 1
    assert discarded.status_code == 200
    assert discarded.json()["total"] == 1

    with get_session_factory()() as session:
        analysis = session.scalar(select(MatchAnalysis))
        notification_count = session.scalar(select(func.count()).select_from(Notification))
        assert analysis is not None
        assert analysis.classification == Classification.DISCARD
        assert analysis.analyzer_version == "rules-v2"
        assert notification_count == 0
        results = analysis.rule_results["results"]
        seniority = next(item for item in results if item["code"] == "SENIORITY_TITLE")
        assert seniority["severity"] == "HARD"


def test_worker_creates_review_analysis_and_daily_review_notification() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "matching-review",
            {
                "title": "Strategic HR Business Partner",
                "company": "Example Corp",
                "location": "Lima",
                "work_mode": "hybrid",
                "url": "https://example.com/jobs/strategic-hrbp",
            },
        )

    with get_session_factory()() as session:
        analysis = session.scalar(select(MatchAnalysis))
        profile = session.scalar(select(CandidateProfile))
        tasks = list(session.scalars(select(ProcessingTask).order_by(ProcessingTask.created_at)))
        notifications = list(
            session.scalars(select(Notification).order_by(Notification.channel.asc()))
        )

        assert analysis is not None
        assert analysis.classification == Classification.REVIEW
        assert analysis.analyzer_version == "rules-v2"
        assert analysis.confidence is not None
        assert profile is not None
        assert profile.salary_min_pen == Decimal("7000")
        assert profile.remote_salary_multiplier == Decimal("1.10")
        assert [task.task_type for task in tasks] == [
            TaskType.NORMALIZE_INGESTION,
            TaskType.ANALYZE_MATCH,
        ]
        assert all(task.status == TaskStatus.COMPLETED for task in tasks)
        assert len(notifications) == 2
        assert all(item.status == NotificationStatus.PENDING for item in notifications)

        by_channel = {item.channel: item for item in notifications}
        dashboard = by_channel[NotificationChannel.DASHBOARD]
        telegram = by_channel[NotificationChannel.TELEGRAM]
        assert dashboard.notification_type == NotificationType.IMMEDIATE
        assert telegram.notification_type == NotificationType.DAILY_REVIEW
        assert telegram.scheduled_for is not None
        assert telegram.scheduled_for.astimezone(ZoneInfo("America/Lima")).hour == 21


def test_strong_role_and_core_area_are_promoted_to_high_priority() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "matching-high-priority",
            {
                "title": "Senior People Analytics Analyst",
                "company": "Analytics Corp",
                "location": "Lima",
                "work_mode": "hybrid",
                "salary_text": "S/ 9,000",
                "description": (
                    "Lidera People Analytics y HR Analytics para decisiones estratégicas de "
                    "gestión humana."
                ),
                "url": "https://example.com/jobs/high-people-analytics",
            },
        )
        summary = client.get("/api/v1/radar/summary")
        high = client.get("/api/v1/radar/jobs?view=high")

    assert summary.status_code == 200
    assert summary.json()["high"] == 1
    assert high.status_code == 200
    assert high.json()["total"] == 1

    with get_session_factory()() as session:
        analysis = session.scalar(select(MatchAnalysis))
        notifications = list(session.scalars(select(Notification)))
        assert analysis is not None
        assert analysis.classification == Classification.HIGH_PRIORITY
        assert analysis.analyzer_version == "rules-v2"
        assert analysis.recommendation == "PRIORIZAR"
        assert "Senior Analyst" in analysis.skill_analysis["role_matches"]
        assert "People Analytics" in analysis.skill_analysis["core_area_matches"]
        assert analysis.strengths
        assert len(notifications) == 2
        assert {item.channel for item in notifications} == {
            NotificationChannel.DASHBOARD,
            NotificationChannel.TELEGRAM,
        }
        assert all(item.notification_type == NotificationType.IMMEDIATE for item in notifications)
        assert all(item.status == NotificationStatus.PENDING for item in notifications)


def test_remote_latam_salary_below_remote_floor_is_discarded() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "matching-remote-salary",
            {
                "title": "Senior People Analytics Analyst",
                "company": "Remote Corp",
                "location": "Remote LATAM",
                "work_mode": "remote",
                "salary_text": "S/ 7,500",
                "url": "https://example.com/jobs/remote-people-analytics",
            },
        )

    with get_session_factory()() as session:
        analysis = session.scalar(select(MatchAnalysis))
        notification_count = session.scalar(select(func.count()).select_from(Notification))
        assert analysis is not None
        assert analysis.classification == Classification.DISCARD
        assert notification_count == 0
        salary_rule = next(
            item
            for item in analysis.rule_results["results"]
            if item["code"] == "PUBLISHED_SALARY"
        )
        assert salary_rule["severity"] == "HARD"
