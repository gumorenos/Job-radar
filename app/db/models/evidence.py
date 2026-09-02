from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import EvidenceSourceType, EvidenceVerificationStatus
from app.db.models.mixins import TimestampMixin


class CareerEvidence(TimestampMixin, Base):
    __tablename__ = "career_evidence"
    __table_args__ = (
        Index(
            "ix_career_evidence_profile_status",
            "candidate_profile_id",
            "verification_status",
        ),
        Index(
            "ix_career_evidence_profile_archived",
            "candidate_profile_id",
            "archived_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    candidate_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False, default="OTHER")
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_type: Mapped[EvidenceSourceType] = mapped_column(
        Enum(EvidenceSourceType, native_enum=False, length=32),
        nullable=False,
        default=EvidenceSourceType.MANUAL,
    )
    verification_status: Mapped[EvidenceVerificationStatus] = mapped_column(
        Enum(EvidenceVerificationStatus, native_enum=False, length=32),
        nullable=False,
        default=EvidenceVerificationStatus.UNVERIFIED,
    )
    generated_by_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    source_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
