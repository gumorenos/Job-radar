from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.enums import EvidenceSourceType, EvidenceVerificationStatus
from app.db.session import get_session
from app.domains.evidence.schemas import (
    CareerEvidenceCreate,
    CareerEvidenceList,
    CareerEvidenceUpdate,
    CareerEvidenceView,
    EvidenceVerificationRequest,
)
from app.domains.evidence.service import (
    archive_evidence,
    create_evidence,
    list_evidence,
    set_evidence_verification,
    update_evidence,
)

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=CareerEvidenceList)
def evidence_list(
    session: SessionDep,
    verification_status: EvidenceVerificationStatus | None = Query(default=None),
    source_type: EvidenceSourceType | None = Query(default=None),
    tag: str | None = Query(default=None, max_length=80),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CareerEvidenceList:
    cleaned_tag = tag.strip() if tag else None
    return list_evidence(
        session,
        verification_status=verification_status,
        source_type=source_type,
        tag=cleaned_tag or None,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CareerEvidenceView, status_code=status.HTTP_201_CREATED)
def evidence_create(
    payload: CareerEvidenceCreate,
    session: SessionDep,
) -> CareerEvidenceView:
    evidence = create_evidence(session, payload)
    session.commit()
    session.refresh(evidence)
    return CareerEvidenceView.model_validate(evidence)


@router.patch("/{evidence_id}", response_model=CareerEvidenceView)
def evidence_update(
    evidence_id: UUID,
    payload: CareerEvidenceUpdate,
    session: SessionDep,
) -> CareerEvidenceView:
    try:
        evidence = update_evidence(session, evidence_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    session.refresh(evidence)
    return CareerEvidenceView.model_validate(evidence)


@router.post("/{evidence_id}/verification", response_model=CareerEvidenceView)
def evidence_verify(
    evidence_id: UUID,
    payload: EvidenceVerificationRequest,
    session: SessionDep,
) -> CareerEvidenceView:
    try:
        evidence = set_evidence_verification(session, evidence_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    session.refresh(evidence)
    return CareerEvidenceView.model_validate(evidence)


@router.post("/{evidence_id}/archive", response_model=CareerEvidenceView)
def evidence_archive(
    evidence_id: UUID,
    session: SessionDep,
) -> CareerEvidenceView:
    try:
        evidence = archive_evidence(session, evidence_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.commit()
    session.refresh(evidence)
    return CareerEvidenceView.model_validate(evidence)
