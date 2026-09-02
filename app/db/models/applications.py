from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import ApplicationStage
from app.db.models.mixins import TimestampMixin


class JobApplication(TimestampMixin, Base):
    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_job_applications_job_id"),
        Index("ix_job_applications_stage_updated", "stage", "updated_at"),
        Index("ix_job_applications_next_action_due", "next_action_due_at"),
        Index("ix_job_applications_follow_up_due", "follow_up_due_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[ApplicationStage] = mapped_column(
        Enum(ApplicationStage, native_enum=False, length=24),
        nullable=False,
        default=ApplicationStage.TO_APPLY,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_action: Mapped[str | None] = mapped_column(Text)
    next_action_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobApplicationEvent(TimestampMixin, Base):
    __tablename__ = "job_application_events"
    __table_args__ = (
        Index("ix_job_application_events_application_created", "application_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_stage: Mapped[str | None] = mapped_column(String(24))
    to_stage: Mapped[str | None] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(Text)
