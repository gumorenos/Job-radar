from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import CvApprovalStatus
from app.db.models.mixins import TimestampMixin


class CandidateProfile(TimestampMixin, Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    salary_min_pen: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=7000)
    remote_salary_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("1.10")
    )
    experience_years: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    degrees: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    transferable_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    target_locations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    target_roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    target_areas: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    adjacent_areas: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    rules: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    daily_review_time: Mapped[time] = mapped_column(Time, nullable=False, default=time(21, 0))
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Lima")


class CvVersion(TimestampMixin, Base):
    __tablename__ = "cv_versions"
    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_id",
            "slug",
            "version",
            name="uq_cv_versions_profile_slug_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    candidate_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    parent_cv_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cv_versions.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_base: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_status: Mapped[CvApprovalStatus] = mapped_column(
        Enum(CvApprovalStatus, native_enum=False, length=24),
        nullable=False,
        default=CvApprovalStatus.DRAFT,
    )
    generated_by_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_role: Mapped[str | None] = mapped_column(String(200))
    target_area: Mapped[str | None] = mapped_column(String(200))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    storage_path: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
