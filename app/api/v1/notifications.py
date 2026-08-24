from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.enums import Classification, NotificationChannel, NotificationStatus, NotificationType
from app.db.models import Company, Job, MatchAnalysis, Notification
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])
SessionDep = Annotated[Session, Depends(get_session)]


class NotificationItem(BaseModel):
    id: UUID
    job_id: UUID
    match_analysis_id: UUID | None
    title: str
    company: str | None
    channel: NotificationChannel
    notification_type: NotificationType
    scheduled_for: datetime | None
    sent_at: datetime | None
    read_at: datetime | None
    status: NotificationStatus
    error_message: str | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationItem]
    total: int


class NotificationSummary(BaseModel):
    pending: int
    sent: int
    failed: int
    skipped: int


class NotificationInboxItem(BaseModel):
    id: UUID
    job_id: UUID
    title: str
    company: str | None
    classification: Classification | None
    recommendation: str | None
    notification_type: NotificationType
    sent_at: datetime | None
    read_at: datetime | None
    created_at: datetime


class NotificationInbox(BaseModel):
    items: list[NotificationInboxItem]
    total: int
    unread: int


class NotificationInboxSummary(BaseModel):
    total: int
    unread: int


class MarkNotificationsReadResponse(BaseModel):
    updated: int
    read_at: datetime


def _company_name(company: Company | None, job: Job) -> str | None:
    return company.name if company is not None else job.company_name_raw


def _item(notification: Notification, job: Job, company: Company | None) -> NotificationItem:
    return NotificationItem(
        id=notification.id,
        job_id=notification.job_id,
        match_analysis_id=notification.match_analysis_id,
        title=job.canonical_title or "Sin título",
        company=_company_name(company, job),
        channel=notification.channel,
        notification_type=notification.notification_type,
        scheduled_for=notification.scheduled_for,
        sent_at=notification.sent_at,
        read_at=notification.read_at,
        status=notification.status,
        error_message=notification.error_message,
        created_at=notification.created_at,
    )


def _inbox_item(
    notification: Notification,
    job: Job,
    company: Company | None,
    analysis: MatchAnalysis | None,
) -> NotificationInboxItem:
    return NotificationInboxItem(
        id=notification.id,
        job_id=notification.job_id,
        title=job.canonical_title or "Sin título",
        company=_company_name(company, job),
        classification=analysis.classification if analysis is not None else None,
        recommendation=analysis.recommendation if analysis is not None else None,
        notification_type=notification.notification_type,
        sent_at=notification.sent_at,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def _dashboard_counts(session: Session) -> tuple[int, int]:
    total = int(
        session.scalar(
            select(func.count(Notification.id)).where(
                Notification.channel == NotificationChannel.DASHBOARD
            )
        )
        or 0
    )
    unread = int(
        session.scalar(
            select(func.count(Notification.id)).where(
                Notification.channel == NotificationChannel.DASHBOARD,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )
    return total, unread


@router.get("/summary", response_model=NotificationSummary)
def notification_summary(session: SessionDep) -> NotificationSummary:
    rows = session.execute(
        select(Notification.status, func.count(Notification.id)).group_by(Notification.status)
    ).all()
    counts = {notification_status: count for notification_status, count in rows}
    return NotificationSummary(
        pending=counts.get(NotificationStatus.PENDING, 0),
        sent=counts.get(NotificationStatus.SENT, 0),
        failed=counts.get(NotificationStatus.FAILED, 0),
        skipped=counts.get(NotificationStatus.SKIPPED, 0),
    )


@router.get("/inbox/summary", response_model=NotificationInboxSummary)
def notification_inbox_summary(session: SessionDep) -> NotificationInboxSummary:
    total, unread = _dashboard_counts(session)
    return NotificationInboxSummary(total=total, unread=unread)


@router.get("/inbox", response_model=NotificationInbox)
def notification_inbox(
    session: SessionDep,
    unread_only: bool = False,
    limit: int = Query(default=40, ge=1, le=100),
) -> NotificationInbox:
    filters = [Notification.channel == NotificationChannel.DASHBOARD]
    if unread_only:
        filters.append(Notification.read_at.is_(None))

    total, unread = _dashboard_counts(session)
    rows = session.execute(
        select(Notification, Job, Company, MatchAnalysis)
        .join(Job, Notification.job_id == Job.id)
        .outerjoin(Company, Job.company_id == Company.id)
        .outerjoin(MatchAnalysis, Notification.match_analysis_id == MatchAnalysis.id)
        .where(*filters)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    ).all()
    return NotificationInbox(
        items=[
            _inbox_item(notification, job, company, analysis)
            for notification, job, company, analysis in rows
        ],
        total=total,
        unread=unread,
    )


@router.post("/inbox/read-all", response_model=MarkNotificationsReadResponse)
def mark_all_dashboard_notifications_read(session: SessionDep) -> MarkNotificationsReadResponse:
    now = datetime.now(UTC)
    updated_ids = list(
        session.scalars(
            update(Notification)
            .where(
                Notification.channel == NotificationChannel.DASHBOARD,
                Notification.read_at.is_(None),
            )
            .values(read_at=now)
            .returning(Notification.id)
        )
    )
    session.commit()
    return MarkNotificationsReadResponse(updated=len(updated_ids), read_at=now)


@router.post("/{notification_id}/read", response_model=MarkNotificationsReadResponse)
def mark_dashboard_notification_read(
    notification_id: UUID,
    session: SessionDep,
) -> MarkNotificationsReadResponse:
    notification = session.get(Notification, notification_id)
    if notification is None or notification.channel != NotificationChannel.DASHBOARD:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificación no encontrada.",
        )

    now = notification.read_at or datetime.now(UTC)
    updated = 0
    if notification.read_at is None:
        notification.read_at = now
        session.commit()
        updated = 1
    return MarkNotificationsReadResponse(updated=updated, read_at=now)


@router.get("", response_model=NotificationList)
def list_notifications(
    session: SessionDep,
    status: NotificationStatus | None = None,
    channel: NotificationChannel | None = None,
    notification_type: NotificationType | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> NotificationList:
    filters = []
    if status is not None:
        filters.append(Notification.status == status)
    if channel is not None:
        filters.append(Notification.channel == channel)
    if notification_type is not None:
        filters.append(Notification.notification_type == notification_type)

    total = session.scalar(select(func.count(Notification.id)).where(*filters)) or 0
    query = (
        select(Notification, Job, Company)
        .join(Job, Notification.job_id == Job.id)
        .outerjoin(Company, Job.company_id == Company.id)
        .where(*filters)
        .order_by(Notification.scheduled_for.asc(), Notification.created_at.asc())
        .limit(limit)
    )
    rows = session.execute(query).all()
    return NotificationList(
        items=[_item(notification, job, company) for notification, job, company in rows],
        total=int(total),
    )
