from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db.models import CandidateProfile
from app.db.session import get_session
from app.domains.profiles.service import get_or_create_active_profile

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])
SessionDep = Annotated[Session, Depends(get_session)]


class CandidateProfileView(BaseModel):
    id: UUID
    name: str
    salary_min_pen: Decimal
    remote_salary_multiplier: Decimal
    remote_salary_min_pen: Decimal
    target_locations: list[str]
    target_roles: list[str]
    target_areas: list[str]
    adjacent_areas: list[str]
    daily_review_time: time
    timezone: str
    rules: dict[str, object]


class CandidateProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    salary_min_pen: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    remote_salary_multiplier: Decimal = Field(ge=1, le=5, max_digits=5, decimal_places=2)
    target_locations: list[str]
    target_roles: list[str]
    target_areas: list[str]
    adjacent_areas: list[str]
    daily_review_time: time
    timezone: str = Field(min_length=1, max_length=80)

    @field_validator(
        "target_locations",
        "target_roles",
        "target_areas",
        "adjacent_areas",
        mode="before",
    )
    @classmethod
    def clean_terms(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("Debe ser una lista.")
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in value:
            if not isinstance(raw, str):
                raise ValueError("Cada elemento debe ser texto.")
            term = raw.strip()
            if not term:
                continue
            if len(term) > 200:
                raise ValueError("Cada término debe tener como máximo 200 caracteres.")
            key = term.casefold()
            if key not in seen:
                cleaned.append(term)
                seen.add(key)
        if len(cleaned) > 100:
            raise ValueError("Se permiten como máximo 100 términos por grupo.")
        return cleaned

    @field_validator("name", "timezone")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El valor no puede estar vacío.")
        return cleaned


def _view(profile: CandidateProfile) -> CandidateProfileView:
    return CandidateProfileView(
        id=profile.id,
        name=profile.name,
        salary_min_pen=profile.salary_min_pen,
        remote_salary_multiplier=profile.remote_salary_multiplier,
        remote_salary_min_pen=(profile.salary_min_pen * profile.remote_salary_multiplier),
        target_locations=list(profile.target_locations),
        target_roles=list(profile.target_roles),
        target_areas=list(profile.target_areas),
        adjacent_areas=list(profile.adjacent_areas),
        daily_review_time=profile.daily_review_time,
        timezone=profile.timezone,
        rules=dict(profile.rules),
    )


@router.get("", response_model=CandidateProfileView)
def get_profile(session: SessionDep) -> CandidateProfileView:
    profile = get_or_create_active_profile(session)
    session.commit()
    session.refresh(profile)
    return _view(profile)


@router.put("", response_model=CandidateProfileView)
def update_profile(
    payload: CandidateProfileUpdate,
    session: SessionDep,
) -> CandidateProfileView:
    profile = get_or_create_active_profile(session)
    profile.name = payload.name
    profile.salary_min_pen = payload.salary_min_pen
    profile.remote_salary_multiplier = payload.remote_salary_multiplier
    profile.target_locations = payload.target_locations
    profile.target_roles = payload.target_roles
    profile.target_areas = payload.target_areas
    profile.adjacent_areas = payload.adjacent_areas
    profile.daily_review_time = payload.daily_review_time
    profile.timezone = payload.timezone
    session.commit()
    session.refresh(profile)
    return _view(profile)
