from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import ApplicationStage
from app.db.models import Company, Job, JobApplication
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])
SessionDep = Annotated[Session, Depends(get_session)]
ApplicationRow = tuple[JobApplication, Job, Company | None]


class ApplicationItem(BaseModel):
    id: UUID
    job_id: UUID
    stage: ApplicationStage
    title: str
    company: str | None
    location: str | None
    notes: str | None
    applied_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationList(BaseModel):
    items: list[ApplicationItem]
    total: int
    stage: ApplicationStage | None


class ApplicationSummary(BaseModel):
    to_apply: int
    applied: int
    interview: int
    offer: int
    closed: int


class ApplicationCreateResponse(BaseModel):
    created: bool
    application: ApplicationItem


class ApplicationUpdateRequest(BaseModel):
    stage: ApplicationStage | None = None
    notes: str | None = Field(default=None, max_length=5000)


def _company_name(company: Company | None, job: Job) -> str | None:
    return company.name if company is not None else job.company_name_raw


def _item(application: JobApplication, job: Job, company: Company | None) -> ApplicationItem:
    return ApplicationItem(
        id=application.id,
        job_id=job.id,
        stage=application.stage,
        title=job.canonical_title or "Sin título",
        company=_company_name(company, job),
        location=job.location_text,
        notes=application.notes,
        applied_at=application.applied_at,
        closed_at=application.closed_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


def _application_row(session: Session, application_id: UUID) -> ApplicationRow | None:
    row = session.execute(
        select(JobApplication, Job, Company)
        .join(Job, JobApplication.job_id == Job.id)
        .outerjoin(Company, Job.company_id == Company.id)
        .where(JobApplication.id == application_id)
    ).one_or_none()
    if row is None:
        return None
    application, job, company = row
    return application, job, company


def _application_for_job(session: Session, job_id: UUID) -> ApplicationRow | None:
    row = session.execute(
        select(JobApplication, Job, Company)
        .join(Job, JobApplication.job_id == Job.id)
        .outerjoin(Company, Job.company_id == Company.id)
        .where(JobApplication.job_id == job_id)
    ).one_or_none()
    if row is None:
        return None
    application, job, company = row
    return application, job, company


@router.get("/summary", response_model=ApplicationSummary)
def application_summary(session: SessionDep) -> ApplicationSummary:
    counts = {stage: 0 for stage in ApplicationStage}
    for stage in session.scalars(select(JobApplication.stage)):
        counts[stage] += 1
    return ApplicationSummary(
        to_apply=counts[ApplicationStage.TO_APPLY],
        applied=counts[ApplicationStage.APPLIED],
        interview=counts[ApplicationStage.INTERVIEW],
        offer=counts[ApplicationStage.OFFER],
        closed=counts[ApplicationStage.CLOSED],
    )


@router.get("", response_model=ApplicationList)
def list_applications(
    session: SessionDep,
    stage: ApplicationStage | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> ApplicationList:
    query = (
        select(JobApplication, Job, Company)
        .join(Job, JobApplication.job_id == Job.id)
        .outerjoin(Company, Job.company_id == Company.id)
        .order_by(JobApplication.updated_at.desc())
        .limit(limit)
    )
    count_query = select(func.count(JobApplication.id))
    if stage is not None:
        query = query.where(JobApplication.stage == stage)
        count_query = count_query.where(JobApplication.stage == stage)

    rows = session.execute(query).all()
    total = int(session.scalar(count_query) or 0)
    return ApplicationList(
        items=[_item(application, job, company) for application, job, company in rows],
        total=total,
        stage=stage,
    )


@router.get("/by-job/{job_id}", response_model=ApplicationItem | None)
def get_application_by_job(job_id: UUID, session: SessionDep) -> ApplicationItem | None:
    if session.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    row = _application_for_job(session, job_id)
    return _item(*row) if row is not None else None


@router.post("/jobs/{job_id}", response_model=ApplicationCreateResponse)
def add_job_to_applications(job_id: UUID, session: SessionDep) -> ApplicationCreateResponse:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    existing = _application_for_job(session, job_id)
    if existing is not None:
        return ApplicationCreateResponse(created=False, application=_item(*existing))

    application = JobApplication(job_id=job_id, stage=ApplicationStage.TO_APPLY)
    session.add(application)
    session.commit()
    row = _application_row(session, application.id)
    if row is None:
        raise RuntimeError("Application disappeared after creation.")
    return ApplicationCreateResponse(created=True, application=_item(*row))


@router.patch("/{application_id}", response_model=ApplicationItem)
def update_application(
    application_id: UUID,
    payload: ApplicationUpdateRequest,
    session: SessionDep,
) -> ApplicationItem:
    application = session.get(JobApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    if "stage" in payload.model_fields_set and payload.stage is not None:
        now = datetime.now(UTC)
        application.stage = payload.stage
        if payload.stage in {
            ApplicationStage.APPLIED,
            ApplicationStage.INTERVIEW,
            ApplicationStage.OFFER,
        } and application.applied_at is None:
            application.applied_at = now
        application.closed_at = now if payload.stage == ApplicationStage.CLOSED else None

    if "notes" in payload.model_fields_set:
        application.notes = (
            payload.notes.strip() if payload.notes and payload.notes.strip() else None
        )

    session.commit()
    row = _application_row(session, application_id)
    if row is None:
        raise RuntimeError("Application disappeared after update.")
    return _item(*row)
