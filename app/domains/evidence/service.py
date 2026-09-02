from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import EvidenceSourceType, EvidenceVerificationStatus
from app.db.models import CareerEvidence
from app.domains.evidence.schemas import (
    CareerEvidenceCreate,
    CareerEvidenceList,
    CareerEvidenceUpdate,
    CareerEvidenceView,
    EvidenceVerificationRequest,
)
from app.domains.profiles.service import get_or_create_active_profile

_CLAIM_FIELDS = {
    "statement",
    "category",
    "tags",
    "source_reference",
    "source_excerpt",
    "source_metadata",
}


def _get_profile_evidence(session: Session, evidence_id: UUID) -> CareerEvidence:
    profile = get_or_create_active_profile(session)
    evidence = session.scalar(
        select(CareerEvidence).where(
            CareerEvidence.id == evidence_id,
            CareerEvidence.candidate_profile_id == profile.id,
        )
    )
    if evidence is None:
        raise LookupError("La evidencia no existe para el perfil activo.")
    return evidence


def create_evidence(session: Session, payload: CareerEvidenceCreate) -> CareerEvidence:
    profile = get_or_create_active_profile(session)
    evidence = CareerEvidence(
        candidate_profile_id=profile.id,
        statement=payload.statement,
        category=payload.category,
        tags=payload.tags,
        source_type=payload.source_type,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
        generated_by_ai=payload.generated_by_ai,
        source_reference=payload.source_reference,
        source_excerpt=payload.source_excerpt,
        source_metadata=payload.source_metadata,
        notes=payload.notes,
    )
    session.add(evidence)
    session.flush()
    return evidence


def list_evidence(
    session: Session,
    *,
    verification_status: EvidenceVerificationStatus | None,
    source_type: EvidenceSourceType | None,
    tag: str | None,
    include_archived: bool,
    limit: int,
    offset: int,
) -> CareerEvidenceList:
    profile = get_or_create_active_profile(session)
    filters = [CareerEvidence.candidate_profile_id == profile.id]
    if not include_archived:
        filters.append(CareerEvidence.archived_at.is_(None))
    if verification_status is not None:
        filters.append(CareerEvidence.verification_status == verification_status)
    if source_type is not None:
        filters.append(CareerEvidence.source_type == source_type)
    if tag:
        filters.append(CareerEvidence.tags.contains([tag]))

    total = session.scalar(select(func.count(CareerEvidence.id)).where(*filters)) or 0
    evidence_rows = list(
        session.scalars(
            select(CareerEvidence)
            .where(*filters)
            .order_by(CareerEvidence.created_at.desc(), CareerEvidence.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    items = [CareerEvidenceView.model_validate(item) for item in evidence_rows]
    return CareerEvidenceList(items=items, total=total, limit=limit, offset=offset)


def update_evidence(
    session: Session,
    evidence_id: UUID,
    payload: CareerEvidenceUpdate,
) -> CareerEvidence:
    evidence = _get_profile_evidence(session, evidence_id)
    if evidence.archived_at is not None:
        raise ValueError("La evidencia archivada no se puede editar.")

    fields = payload.model_fields_set
    if evidence.verification_status == EvidenceVerificationStatus.VERIFIED and (
        fields & _CLAIM_FIELDS
    ):
        raise ValueError(
            "Una evidencia verificada es inmutable. Archívala y crea una nueva versión."
        )

    for field in fields:
        value = getattr(payload, field)
        if field in {"statement", "category"} and value is None:
            raise ValueError(f"{field} no puede ser nulo.")
        setattr(evidence, field, value)

    if fields & _CLAIM_FIELDS and evidence.verification_status != EvidenceVerificationStatus.UNVERIFIED:
        evidence.verification_status = EvidenceVerificationStatus.UNVERIFIED
        evidence.reviewed_at = None
        evidence.verified_at = None

    session.flush()
    return evidence


def set_evidence_verification(
    session: Session,
    evidence_id: UUID,
    payload: EvidenceVerificationRequest,
) -> CareerEvidence:
    evidence = _get_profile_evidence(session, evidence_id)
    if evidence.archived_at is not None:
        raise ValueError("La evidencia archivada no se puede verificar.")

    now = datetime.now(UTC)
    evidence.verification_status = payload.status
    evidence.reviewed_at = now
    evidence.verified_at = now if payload.status == EvidenceVerificationStatus.VERIFIED else None
    if payload.notes is not None:
        evidence.notes = payload.notes
    session.flush()
    return evidence


def archive_evidence(session: Session, evidence_id: UUID) -> CareerEvidence:
    evidence = _get_profile_evidence(session, evidence_id)
    if evidence.archived_at is None:
        evidence.archived_at = datetime.now(UTC)
        session.flush()
    return evidence
