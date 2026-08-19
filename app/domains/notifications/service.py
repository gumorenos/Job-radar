from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import (
    Classification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)
from app.db.models import CandidateProfile, MatchAnalysis, Notification


def _profile_timezone(profile: CandidateProfile) -> ZoneInfo:
    try:
        return ZoneInfo(profile.timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def next_daily_review_at(
    profile: CandidateProfile,
    *,
    now: datetime | None = None,
) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)

    zone = _profile_timezone(profile)
    local_now = current.astimezone(zone)
    local_target = datetime.combine(
        local_now.date(),
        profile.daily_review_time,
        tzinfo=zone,
    )
    if local_target <= local_now:
        local_target += timedelta(days=1)
    return local_target.astimezone(UTC)


def _notification(
    analysis: MatchAnalysis,
    channel: NotificationChannel,
    notification_type: NotificationType,
    scheduled_for: datetime,
) -> Notification:
    return Notification(
        job_id=analysis.job_id,
        match_analysis_id=analysis.id,
        channel=channel,
        notification_type=notification_type,
        scheduled_for=scheduled_for,
        status=NotificationStatus.PENDING,
    )


def plan_match_notifications(
    session: Session,
    analysis: MatchAnalysis,
    profile: CandidateProfile,
    *,
    now: datetime | None = None,
) -> list[Notification]:
    existing = list(
        session.scalars(
            select(Notification)
            .where(Notification.match_analysis_id == analysis.id)
            .order_by(Notification.created_at.asc())
        )
    )
    if existing:
        return existing

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)

    notifications: list[Notification] = []
    if analysis.classification == Classification.HIGH_PRIORITY:
        notifications = [
            _notification(
                analysis,
                NotificationChannel.DASHBOARD,
                NotificationType.IMMEDIATE,
                current,
            ),
            _notification(
                analysis,
                NotificationChannel.TELEGRAM,
                NotificationType.IMMEDIATE,
                current,
            ),
        ]
    elif analysis.classification == Classification.REVIEW:
        notifications = [
            _notification(
                analysis,
                NotificationChannel.DASHBOARD,
                NotificationType.IMMEDIATE,
                current,
            ),
            _notification(
                analysis,
                NotificationChannel.TELEGRAM,
                NotificationType.DAILY_REVIEW,
                next_daily_review_at(profile, now=current),
            ),
        ]

    session.add_all(notifications)
    session.flush()
    return notifications
