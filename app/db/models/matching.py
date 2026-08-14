from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import Classification, Confidence, FeedbackReason
from app.db.models.mixins import TimestampMixin


class MatchAnalysis(Base):
    __tablename__ = "match_analyses"
    __table_args__ = (Index("ix_match_analyses_job_created", "job_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    cv_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cv_versions.id", ondelete="SET NULL")
    )
    overall_score: Mapped[int | None] = mapped_column(Integer)
    classification: Mapped[Classification | None] = mapped_column(
        Enum(Classification, native_enum=False, length=24)
    )
    confidence: Mapped[Confidence | None] = mapped_column(
        Enum(Confidence, native_enum=False, length=16)
    )
    rule_results: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    skill_analysis: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    strengths: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    gaps: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    career_move_assessment: Mapped[str | None] = mapped_column(Text)
    salary_assessment: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(String(120))
    explanation: Mapped[str | None] = mapped_column(Text)
    analyzer_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ClassificationFeedback(TimestampMixin, Base):
    __tablename__ = "classification_feedback"
    __table_args__ = (Index("ix_classification_feedback_job_created", "job_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("match_analyses.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    system_classification: Mapped[Classification] = mapped_column(
        Enum(Classification, native_enum=False, length=24), nullable=False
    )
    human_classification: Mapped[Classification] = mapped_column(
        Enum(Classification, native_enum=False, length=24), nullable=False
    )
    reason_code: Mapped[FeedbackReason] = mapped_column(
        Enum(FeedbackReason, native_enum=False, length=24), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text)
