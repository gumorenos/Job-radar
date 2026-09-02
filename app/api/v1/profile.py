from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import JobStatus
from app.db.models import CandidateProfile, Job
from app.db.session import get_session
from app.domains.matching.queue import ensure_pending_job_analyses
from app.domains.matching.rules import (
    HardRuleToggles,
    hard_rule_toggles_from_metadata,
    with_hard_rule_toggles,
)
from app.domains.profiles.service import get_or_create_active_profile

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])
SessionDep = Annotated[Session, Depends(get_session)]


class HardRuleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discard_disallowed_titles: bool = True
    discard_onsite_outside_lima: bool = True
    discard_published_salary_below_floor: bool = True


class CandidateProfileView(BaseModel):
    id: UUID
    name: str
    salary_min_pen: Decimal
    remote_salary_multiplier: Decimal
    remote_salary_min_pen: Decimal
    experience_years: Decimal | None
    degrees: list[str]
    skills: list[str]
    transferable_skills: list[str]
    target_locations: list[str]
    target_roles: list[str]
    target_areas: list[str]
    adjacent_areas: list[str]
    daily_review_time: time
    timezone: str
    hard_rules: HardRuleSettings
    rules: dict[str, object]


class CandidateProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    salary_min_pen: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    remote_salary_multiplier: Decimal = Field(ge=1, le=5, max_digits=5, decimal_places=2)
    experience_years: Decimal | None = Field(default=None, ge=0, le=80, decimal_places=2)
    degrees: list[str]
    skills: list[str]
    transferable_skills: list[str]
    target_locations: list[str]
    target_roles: list[str]
    target_areas: list[str]
    adjacent_areas: list[str]
    daily_review_time: time
    timezone: str = Field(min_length=1, max_length=80)
    hard_rules: HardRuleSettings | None = None

    @field_validator(
        "degrees",
        "skills",
        "transferable_skills",
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

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre no puede estar vacío.")
        return cleaned

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("La zona horaria no puede estar vacía.")
        try:
            ZoneInfo(cleaned)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Usa una zona horaria IANA válida, por ejemplo America/Lima.") from exc
        return cleaned


class ProfileReanalysisResponse(BaseModel):
    jobs_considered: int
    enqueued: int
    reused_pending: int


def _view(profile: CandidateProfile) -> CandidateProfileView:
    hard_rules = hard_rule_toggles_from_metadata(profile.rules)
    return CandidateProfileView(
        id=profile.id,
        name=profile.name,
        salary_min_pen=profile.salary_min_pen,
        remote_salary_multiplier=profile.remote_salary_multiplier,
        remote_salary_min_pen=(profile.salary_min_pen * profile.remote_salary_multiplier),
        experience_years=profile.experience_years,
        degrees=list(profile.degrees),
        skills=list(profile.skills),
        transferable_skills=list(profile.transferable_skills),
        target_locations=list(profile.target_locations),
        target_roles=list(profile.target_roles),
        target_areas=list(profile.target_areas),
        adjacent_areas=list(profile.adjacent_areas),
        daily_review_time=profile.daily_review_time,
        timezone=profile.timezone,
        hard_rules=HardRuleSettings(**hard_rules.as_dict()),
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
    profile.experience_years = payload.experience_years
    profile.degrees = payload.degrees
    profile.skills = payload.skills
    profile.transferable_skills = payload.transferable_skills
    profile.target_locations = payload.target_locations
    profile.target_roles = payload.target_roles
    profile.target_areas = payload.target_areas
    profile.adjacent_areas = payload.adjacent_areas
    profile.daily_review_time = payload.daily_review_time
    profile.timezone = payload.timezone
    if payload.hard_rules is not None:
        profile.rules = with_hard_rule_toggles(
            profile.rules,
            HardRuleToggles(**payload.hard_rules.model_dump()),
        )
    session.commit()
    session.refresh(profile)
    return _view(profile)


@router.post(
    "/reanalyze",
    response_model=ProfileReanalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reanalyze_active_jobs(session: SessionDep) -> ProfileReanalysisResponse:
    # This is deliberately explicit rather than tied to PUT /profile. Saving preferences should
    # not unexpectedly fan out worker tasks or produce classification-change notifications.
    get_or_create_active_profile(session)
    job_ids = list(
        session.scalars(
            select(Job.id)
            .where(Job.status.in_((JobStatus.ACTIVE, JobStatus.UNKNOWN)))
            .order_by(Job.last_seen_at.desc())
        )
    )
    queued = ensure_pending_job_analyses(session, job_ids)
    session.commit()
    return ProfileReanalysisResponse(
        jobs_considered=len(job_ids),
        enqueued=queued.created,
        reused_pending=queued.reused_pending,
    )
