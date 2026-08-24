from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import JobStatus, PostingStatus, WorkMode
from app.db.models.mixins import TimestampMixin


class Company(TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_companies_normalized_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(100))
    is_confidential_placeholder: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_last_seen", "status", "last_seen_at"),
        Index("ix_jobs_company_title_key", "company_id", "title_key"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_title: Mapped[str | None] = mapped_column(String(300))
    title_key: Mapped[str | None] = mapped_column(String(300))
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    company_name_raw: Mapped[str | None] = mapped_column(String(255))
    company_is_confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(120))
    work_mode: Mapped[WorkMode] = mapped_column(
        Enum(WorkMode, native_enum=False, length=16), nullable=False, default=WorkMode.UNKNOWN
    )
    employment_type: Mapped[str | None] = mapped_column(String(120))
    seniority: Mapped[str | None] = mapped_column(String(120))
    required_experience_years: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    required_degrees: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    required_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=16), nullable=False, default=JobStatus.UNKNOWN
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))


class JobPosting(TimestampMixin, Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint(
            "posting_source",
            "source_external_id",
            name="uq_job_postings_source_external_id",
        ),
        Index("ix_job_postings_normalized_url", "source_url_normalized"),
        Index("ix_job_postings_job_status", "job_id", "posting_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    posting_source: Mapped[str | None] = mapped_column(String(80))
    source_external_id: Mapped[str | None] = mapped_column(String(300))
    source_url_raw: Mapped[str | None] = mapped_column(Text)
    source_url_normalized: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    title_raw: Mapped[str | None] = mapped_column(String(300))
    company_raw: Mapped[str | None] = mapped_column(String(255))
    location_raw: Mapped[str | None] = mapped_column(String(255))
    description_raw: Mapped[str | None] = mapped_column(Text)
    salary_text: Mapped[str | None] = mapped_column(String(500))
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(40))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    posting_status: Mapped[PostingStatus] = mapped_column(
        Enum(PostingStatus, native_enum=False, length=16),
        nullable=False,
        default=PostingStatus.UNKNOWN,
    )


class PostingSighting(TimestampMixin, Base):
    __tablename__ = "posting_sightings"
    __table_args__ = (
        UniqueConstraint(
            "ingestion_event_id",
            "job_posting_id",
            name="uq_posting_sightings_event_posting",
        ),
        Index("ix_posting_sightings_posting_seen", "job_posting_id", "seen_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ingestion_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_events.id", ondelete="CASCADE"), nullable=False
    )
    job_posting_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
