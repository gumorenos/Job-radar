from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from app.db.enums import (
    JobStatus,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    TaskType,
    WorkMode,
)
from app.db.models import Job, Notification, ProcessingTask
from app.db.session import get_engine, get_session_factory
from app.domains.notifications import delivery


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


def _job(title: str) -> Job:
    now = datetime.now(UTC)
    return Job(
        canonical_title=title,
        title_key=title.lower(),
        company_name_raw="Delivery Corp",
        company_is_confidential=False,
        location_text="Lima",
        work_mode=WorkMode.HYBRID,
        status=JobStatus.ACTIVE,
        first_seen_at=now,
        last_seen_at=now,
    )


def test_dispatcher_creates_send_task_only_for_due_pending_telegram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        due_job = _job("Due HRBP")
        future_job = _job("Future HRBP")
        session.add_all([due_job, future_job])
        session.flush()
        due = Notification(
            job_id=due_job.id,
            channel=NotificationChannel.TELEGRAM,
            notification_type=NotificationType.IMMEDIATE,
            scheduled_for=now - timedelta(seconds=1),
            status=NotificationStatus.PENDING,
        )
        future = Notification(
            job_id=future_job.id,
            channel=NotificationChannel.TELEGRAM,
            notification_type=NotificationType.IMMEDIATE,
            scheduled_for=now + timedelta(hours=1),
            status=NotificationStatus.PENDING,
        )
        session.add_all([due, future])
        session.commit()
        due_id = due.id

    monkeypatch.setattr(
        delivery,
        "get_settings",
        lambda: SimpleNamespace(telegram_enabled=True),
    )
    with get_session_factory()() as session:
        created = delivery.enqueue_due_telegram_notifications(session, now=now)
        created_again = delivery.enqueue_due_telegram_notifications(session, now=now)

    assert created == 1
    assert created_again == 0
    with get_session_factory()() as session:
        tasks = list(session.scalars(select(ProcessingTask)))
        assert len(tasks) == 1
        assert tasks[0].task_type == TaskType.SEND_NOTIFICATION
        assert tasks[0].entity_id == due_id


def test_daily_review_delivery_is_aggregated_and_marks_batch_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    sent_messages: list[str] = []
    with get_session_factory()() as session:
        jobs = [_job("Strategic HRBP"), _job("People Analytics Lead")]
        session.add_all(jobs)
        session.flush()
        notifications = [
            Notification(
                job_id=job.id,
                channel=NotificationChannel.TELEGRAM,
                notification_type=NotificationType.DAILY_REVIEW,
                scheduled_for=now - timedelta(minutes=1),
                status=NotificationStatus.PENDING,
            )
            for job in jobs
        ]
        session.add_all(notifications)
        session.commit()
        first_id = notifications[0].id

    monkeypatch.setattr(delivery, "send_telegram_message", sent_messages.append)
    with get_session_factory()() as session:
        delivered = delivery.deliver_notification(session, first_id, now=now)
        session.commit()

    assert delivered == 2
    assert len(sent_messages) == 1
    assert "2 oportunidad(es)" in sent_messages[0]
    assert "Strategic HRBP" in sent_messages[0]
    assert "People Analytics Lead" in sent_messages[0]

    with get_session_factory()() as session:
        rows = list(session.scalars(select(Notification)))
        assert all(item.status == NotificationStatus.SENT for item in rows)
        assert all(item.sent_at is not None for item in rows)
