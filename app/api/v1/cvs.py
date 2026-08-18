from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.enums import CvApprovalStatus
from app.db.models import CvVersion
from app.db.session import get_session
from app.domains.profiles.service import get_or_create_active_profile

router = APIRouter(prefix="/api/v1/cvs", tags=["cvs"])
SessionDep = Annotated[Session, Depends(get_session)]
ApprovalDecision = Literal["APPROVED", "REJECTED"]


class CvCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_cv_id: UUID | None = None
    is_base: bool = False
    activate: bool = False
    generated_by_ai: bool = False
    target_role: str | None = Field(default=None, max_length=200)
    target_area: str | None = Field(default=None, max_length=200)
    original_filename: str | None = Field(default=None, max_length=255)
    storage_path: str | None = None
    content_text: str | None = None


class CvApprovalRequest(BaseModel):
    status: ApprovalDecision


class CvItem(BaseModel):
    id: UUID
    candidate_profile_id: UUID
    parent_cv_id: UUID | None
    name: str
    slug: str
    version: int
    is_base: bool
    is_active: bool
    approval_status: str
    generated_by_ai: bool
    approved_at: datetime | None
    target_role: str | None
    target_area: str | None
    original_filename: str | None
    storage_path: str | None
    content_text: str | None
    created_at: datetime
    updated_at: datetime


class CvList(BaseModel):
    items: list[CvItem]
    total: int


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:120] or "cv"


def _item(cv: CvVersion) -> CvItem:
    return CvItem(
        id=cv.id,
        candidate_profile_id=cv.candidate_profile_id,
        parent_cv_id=cv.parent_cv_id,
        name=cv.name,
        slug=cv.slug,
        version=cv.version,
        is_base=cv.is_base,
        is_active=cv.is_active,
        approval_status=cv.approval_status.value,
        generated_by_ai=cv.generated_by_ai,
        approved_at=cv.approved_at,
        target_role=cv.target_role,
        target_area=cv.target_area,
        original_filename=cv.original_filename,
        storage_path=cv.storage_path,
        content_text=cv.content_text,
        created_at=cv.created_at,
        updated_at=cv.updated_at,
    )


def _cv_or_404(session: Session, cv_id: UUID) -> CvVersion:
    cv = session.get(CvVersion, cv_id)
    if cv is None:
        raise HTTPException(status_code=404, detail="CV no encontrado.")
    return cv


@router.get("", response_model=CvList)
def list_cvs(session: SessionDep) -> CvList:
    profile = get_or_create_active_profile(session)
    items = list(
        session.scalars(
            select(CvVersion)
            .where(CvVersion.candidate_profile_id == profile.id)
            .order_by(
                CvVersion.is_base.desc(),
                CvVersion.is_active.desc(),
                CvVersion.updated_at.desc(),
            )
        )
    )
    session.commit()
    return CvList(items=[_item(cv) for cv in items], total=len(items))


@router.get("/{cv_id}", response_model=CvItem)
def get_cv(cv_id: UUID, session: SessionDep) -> CvItem:
    return _item(_cv_or_404(session, cv_id))


@router.post("", response_model=CvItem, status_code=status.HTTP_201_CREATED)
def create_cv(payload: CvCreate, session: SessionDep) -> CvItem:
    profile = get_or_create_active_profile(session)
    name = payload.name.strip()
    slug = _slugify(name)

    parent = None
    if payload.parent_cv_id is not None:
        parent = _cv_or_404(session, payload.parent_cv_id)
        if parent.candidate_profile_id != profile.id:
            raise HTTPException(status_code=409, detail="El CV padre pertenece a otro perfil.")

    current_version = session.scalar(
        select(func.max(CvVersion.version)).where(
            CvVersion.candidate_profile_id == profile.id,
            CvVersion.slug == slug,
        )
    )
    version = int(current_version or 0) + 1

    approval_status = (
        CvApprovalStatus.DRAFT if payload.generated_by_ai else CvApprovalStatus.APPROVED
    )
    approved_at = None if payload.generated_by_ai else datetime.now(UTC)
    if payload.generated_by_ai and (payload.activate or payload.is_base):
        raise HTTPException(
            status_code=409,
            detail=(
                "Un CV generado por IA debe aprobarse antes de reemplazar el CV base o activarse."
            ),
        )

    if payload.is_base:
        session.execute(
            update(CvVersion)
            .where(CvVersion.candidate_profile_id == profile.id)
            .values(is_base=False)
        )
    if payload.activate:
        session.execute(
            update(CvVersion)
            .where(CvVersion.candidate_profile_id == profile.id)
            .values(is_active=False)
        )

    cv = CvVersion(
        candidate_profile_id=profile.id,
        parent_cv_id=parent.id if parent is not None else None,
        name=name,
        slug=slug,
        version=version,
        is_base=payload.is_base,
        is_active=payload.activate,
        approval_status=approval_status,
        generated_by_ai=payload.generated_by_ai,
        approved_at=approved_at,
        target_role=_clean_optional(payload.target_role),
        target_area=_clean_optional(payload.target_area),
        original_filename=_clean_optional(payload.original_filename),
        storage_path=_clean_optional(payload.storage_path),
        content_text=_clean_optional(payload.content_text),
    )
    session.add(cv)
    session.commit()
    session.refresh(cv)
    return _item(cv)


@router.post("/{cv_id}/approval", response_model=CvItem)
def set_cv_approval(
    cv_id: UUID,
    payload: CvApprovalRequest,
    session: SessionDep,
) -> CvItem:
    cv = _cv_or_404(session, cv_id)
    decision = CvApprovalStatus(payload.status)
    cv.approval_status = decision
    cv.approved_at = datetime.now(UTC) if decision == CvApprovalStatus.APPROVED else None
    if decision == CvApprovalStatus.REJECTED:
        cv.is_active = False
    session.commit()
    session.refresh(cv)
    return _item(cv)


@router.post("/{cv_id}/activate", response_model=CvItem)
def activate_cv(cv_id: UUID, session: SessionDep) -> CvItem:
    cv = _cv_or_404(session, cv_id)
    if cv.approval_status != CvApprovalStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Solo un CV aprobado puede activarse.")

    session.execute(
        update(CvVersion)
        .where(CvVersion.candidate_profile_id == cv.candidate_profile_id)
        .values(is_active=False)
    )
    cv.is_active = True
    session.commit()
    session.refresh(cv)
    return _item(cv)
