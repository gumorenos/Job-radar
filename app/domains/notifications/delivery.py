from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.enums import (
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    TaskStatus,
    TaskType,
)
from app.db.models import Company, Job, MatchAnalysis, Notification, ProcessingTask
from app.integrations.telegram import send_telegram_message


def enqueue_due_telegram_notifications(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> int:
    """Create durable send tasks for due Telegram intents when delivery is enabled."""

    if not get_settings().telegram_enabled:
        return 0

    current = now or datetime.now(UTC)
    due = list(
        session.scalars(
            select(Notification)
            .where(
                Notification.channel == NotificationChannel.TELEGRAM,
                Notification.status == NotificationStatus.PENDING,
                Notification.scheduled_for.is_not(None),
                Notification.scheduled_for <= current,
            )
            .order_by(Notification.scheduled_for.asc(), Notification.created_at.asc())
            .limit(limit)
        )
    )
    created = 0
    for notification in due:
        existing = session.scalar(
            select(ProcessingTask.id)
            .where(
                ProcessingTask.task_type == TaskType.SEND_NOTIFICATION,
                ProcessingTask.entity_type == "notification",
                ProcessingTask.entity_id == notification.id,
                ProcessingTask.status.in_((TaskStatus.PENDING, TaskStatus.RUNNING)),
            )
            .limit(1)
        )
        if existing is not None:
            continue
        session.add(
            ProcessingTask(
                task_type=TaskType.SEND_NOTIFICATION,
                entity_type="notification",
                entity_id=notification.id,
                status=TaskStatus.PENDING,
                priority=300,
                scheduled_at=current,
            )
        )
        created += 1

    if created:
        session.commit()
    return created


def _job_label(session: Session, notification: Notification) -> tuple[Job, str | None]:
    job = session.get(Job, notification.job_id)
    if job is None:
        raise LookupError(f"Job {notification.job_id} does not exist for notification.")
    company = session.get(Company, job.company_id) if job.company_id is not None else None
    company_name = company.name if company is not None else job.company_name_raw
    return job, company_name


def _analysis(session: Session, notification: Notification) -> MatchAnalysis | None:
    if notification.match_analysis_id is None:
        return None
    return session.get(MatchAnalysis, notification.match_analysis_id)


def _immediate_message(session: Session, notification: Notification) -> str:
    job, company = _job_label(session, notification)
    analysis = _analysis(session, notification)
    lines = [
        "🔥 Alta prioridad · Job Radar",
        job.canonical_title or "Sin título",
        company or "Empresa no indicada",
    ]
    if job.location_text:
        lines.append(job.location_text)
    if analysis is not None and analysis.explanation:
        lines.extend(("", analysis.explanation))
    return "\n".join(lines)


def _daily_review_message(
    session: Session,
    notifications: list[Notification],
) -> str:
    lines = [
        "🗂 Revisión diaria · Job Radar",
        f"{len(notifications)} oportunidad(es) para revisar.",
        "",
    ]
    visible = notifications[:20]
    for index, notification in enumerate(visible, start=1):
        job, company = _job_label(session, notification)
        lines.append(
            f"{index}. {job.canonical_title or 'Sin título'} — {company or 'Empresa no indicada'}"
        )
    remaining = len(notifications) - len(visible)
    if remaining > 0:
        lines.extend(("", f"+ {remaining} más disponibles en el dashboard."))
    return "\n".join(lines)


def deliver_notification(
    session: Session,
    notification_id: UUID,
    *,
    now: datetime | None = None,
) -> int:
    """Deliver one immediate intent or one aggregated due daily-review batch."""

    notification = session.get(Notification, notification_id)
    if notification is None:
        raise LookupError(f"Notification {notification_id} does not exist.")
    if notification.status != NotificationStatus.PENDING:
        return 0
    if notification.channel != NotificationChannel.TELEGRAM:
        notification.status = NotificationStatus.SKIPPED
        session.flush()
        return 0

    current = now or datetime.now(UTC)
    if notification.notification_type == NotificationType.DAILY_REVIEW:
        batch = list(
            session.scalars(
                select(Notification)
                .where(
                    Notification.channel == NotificationChannel.TELEGRAM,
                    Notification.notification_type == NotificationType.DAILY_REVIEW,
                    Notification.status == NotificationStatus.PENDING,
                    Notification.scheduled_for.is_not(None),
                    Notification.scheduled_for <= current,
                )
                .order_by(Notification.scheduled_for.asc(), Notification.created_at.asc())
            )
        )
        if not batch:
            return 0
        send_telegram_message(_daily_review_message(session, batch))
        for item in batch:
            item.status = NotificationStatus.SENT
            item.sent_at = current
            item.error_message = None
        session.flush()
        return len(batch)

    send_telegram_message(_immediate_message(session, notification))
    notification.status = NotificationStatus.SENT
    notification.sent_at = current
    notification.error_message = None
    session.flush()
    return 1
