from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import NotificationChannel, NotificationStatus, NotificationType
from app.db.models.mixins import TimestampMixin


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_status_scheduled", "status", "scheduled_for"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    match_analysis_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("match_analyses.id", ondelete="SET NULL")
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False, length=24), nullable=False
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, native_enum=False, length=24), nullable=False
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, native_enum=False, length=24),
        nullable=False,
        default=NotificationStatus.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
