from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.enums import ApplicationStage
from app.db.models import Company, Job, JobApplication, JobApplicationEvent
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])
SessionDep = Annotated[Session, Depends(get_session)]
ApplicationRow = tuple[JobApplication, Job, Company | None]

_DEFAULT_NEXT_ACTION = {
    ApplicationStage.TO_APPLY: "Preparar postulación",
    ApplicationStage.APPLIED: "Enviar seguimiento",
    ApplicationStage.INTERVIEW: "Preparar entrevista",
    ApplicationStage.OFFER: "Evaluar oferta",
    ApplicationStage.CLOSED: None,
}


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
    next_action: str | None
    next_action_due_at: datetime | None
    follow_up_due_at: datetime | None
    last_follow_up_at: datetime | None
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
    next_action: str | None = Field(default=None, max_length=500)
    next_action_due_at: datetime | None = None
    follow_up_due_at: datetime | None = None


class FollowUpCompleteRequest(BaseModel):
    next_follow_up_days: int | None = Field(default=7, ge=1, le=60)


class ApplicationEventItem(BaseModel):
    id: UUID
    event_type: str
    from_stage: str | None
    to_stage: str | None
    note: str | None
    occurred_at: datetime


class ApplicationTimeline(BaseModel):
    items: list[ApplicationEventItem]


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
        next_action=application.next_action,
        next_action_due_at=application.next_action_due_at,
        follow_up_due_at=application.follow_up_due_at,
        last_follow_up_at=application.last_follow_up_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


def _event_item(event: JobApplicationEvent) -> ApplicationEventItem:
    return ApplicationEventItem(
        id=event.id,
        event_type=event.event_type,
        from_stage=event.from_stage,
        to_stage=event.to_stage,
        note=event.note,
        occurred_at=event.created_at,
    )


def _append_event(
    session: Session,
    application: JobApplication,
    event_type: str,
    *,
    from_stage: ApplicationStage | None = None,
    to_stage: ApplicationStage | None = None,
    note: str | None = None,
) -> None:
    session.add(
        JobApplicationEvent(
            application_id=application.id,
            event_type=event_type,
            from_stage=from_stage.value if from_stage is not None else None,
            to_stage=to_stage.value if to_stage is not None else None,
            note=note,
        )
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


def _apply_stage_defaults(
    application: JobApplication,
    stage: ApplicationStage,
    now: datetime,
    explicit_fields: set[str],
) -> None:
    if "next_action" not in explicit_fields:
        application.next_action = _DEFAULT_NEXT_ACTION[stage]

    if stage == ApplicationStage.APPLIED:
        due_at = now + timedelta(days=7)
        if "follow_up_due_at" not in explicit_fields:
            application.follow_up_due_at = due_at
        if "next_action_due_at" not in explicit_fields:
            application.next_action_due_at = due_at
    else:
        if "follow_up_due_at" not in explicit_fields:
            application.follow_up_due_at = None
        if "next_action_due_at" not in explicit_fields:
            application.next_action_due_at = None


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
    q: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> ApplicationList:
    query = (
        select(JobApplication, Job, Company)
        .join(Job, JobApplication.job_id == Job.id)
        .outerjoin(Company, Job.company_id == Company.id)
        .order_by(JobApplication.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    count_query = (
        select(func.count(JobApplication.id))
        .join(Job, JobApplication.job_id == Job.id)
        .outerjoin(Company, Job.company_id == Company.id)
    )
    if stage is not None:
        query = query.where(JobApplication.stage == stage)
        count_query = count_query.where(JobApplication.stage == stage)

    search = q.strip() if q else ""
    if search:
        pattern = f"%{search}%"
        condition = or_(
            Job.canonical_title.ilike(pattern),
            Job.company_name_raw.ilike(pattern),
            Company.name.ilike(pattern),
            Job.location_text.ilike(pattern),
            JobApplication.notes.ilike(pattern),
            JobApplication.next_action.ilike(pattern),
        )
        query = query.where(condition)
        count_query = count_query.where(condition)

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

    application = JobApplication(
        job_id=job_id,
        stage=ApplicationStage.TO_APPLY,
        next_action=_DEFAULT_NEXT_ACTION[ApplicationStage.TO_APPLY],
    )
    session.add(application)
    session.flush()
    _append_event(
        session,
        application,
        "CREATED",
        to_stage=ApplicationStage.TO_APPLY,
        note="Añadida a Postulaciones.",
    )
    session.commit()
    row = _application_row(session, application.id)
    if row is None:
        raise RuntimeError("Application disappeared after creation.")
    return ApplicationCreateResponse(created=True, application=_item(*row))


@router.get("/{application_id}/timeline", response_model=ApplicationTimeline)
def application_timeline(application_id: UUID, session: SessionDep) -> ApplicationTimeline:
    if session.get(JobApplication, application_id) is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    events = list(
        session.scalars(
            select(JobApplicationEvent)
            .where(JobApplicationEvent.application_id == application_id)
            .order_by(JobApplicationEvent.created_at.asc(), JobApplicationEvent.id.asc())
        )
    )
    return ApplicationTimeline(items=[_event_item(event) for event in events])


@router.post("/{application_id}/follow-up-complete", response_model=ApplicationItem)
def complete_follow_up(
    application_id: UUID,
    payload: FollowUpCompleteRequest,
    session: SessionDep,
) -> ApplicationItem:
    application = session.get(JobApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    if application.stage != ApplicationStage.APPLIED:
        raise HTTPException(
            status_code=409,
            detail="Follow-up can only be completed while the application is APPLIED.",
        )

    now = datetime.now(UTC)
    had_previous_follow_up = application.last_follow_up_at is not None
    application.last_follow_up_at = now
    if payload.next_follow_up_days is None:
        application.follow_up_due_at = None
        application.next_action_due_at = None
        application.next_action = "Esperar respuesta"
        note = "Seguimiento registrado; sin nuevo seguimiento programado."
    else:
        due_at = now + timedelta(days=payload.next_follow_up_days)
        application.follow_up_due_at = due_at
        application.next_action_due_at = due_at
        application.next_action = (
            "Enviar otro seguimiento" if had_previous_follow_up else "Enviar segundo seguimiento"
        )
        note = f"Seguimiento registrado; próximo en {payload.next_follow_up_days} días."

    _append_event(session, application, "FOLLOW_UP_COMPLETED", note=note)
    session.commit()
    row = _application_row(session, application_id)
    if row is None:
        raise RuntimeError("Application disappeared after follow-up update.")
    return _item(*row)


@router.patch("/{application_id}", response_model=ApplicationItem)
def update_application(
    application_id: UUID,
    payload: ApplicationUpdateRequest,
    session: SessionDep,
) -> ApplicationItem:
    application = session.get(JobApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    explicit_fields = payload.model_fields_set
    previous_stage = application.stage
    stage_changed = False

    if "stage" in explicit_fields and payload.stage is not None:
        stage_changed = payload.stage != application.stage
        if stage_changed:
            now = datetime.now(UTC)
            application.stage = payload.stage
            if payload.stage in {
                ApplicationStage.APPLIED,
                ApplicationStage.INTERVIEW,
                ApplicationStage.OFFER,
            } and application.applied_at is None:
                application.applied_at = now
            application.closed_at = now if payload.stage == ApplicationStage.CLOSED else None
            _apply_stage_defaults(application, payload.stage, now, explicit_fields)

    if "notes" in explicit_fields:
        application.notes = (
            payload.notes.strip() if payload.notes and payload.notes.strip() else None
        )
    if "next_action" in explicit_fields:
        application.next_action = (
            payload.next_action.strip()
            if payload.next_action and payload.next_action.strip()
            else None
        )
    if "next_action_due_at" in explicit_fields:
        application.next_action_due_at = payload.next_action_due_at
    if "follow_up_due_at" in explicit_fields:
        application.follow_up_due_at = payload.follow_up_due_at

    planning_changed = bool(
        explicit_fields & {"next_action", "next_action_due_at", "follow_up_due_at"}
    )
    if stage_changed:
        _append_event(
            session,
            application,
            "STAGE_CHANGED",
            from_stage=previous_stage,
            to_stage=application.stage,
            note=application.next_action,
        )
    elif planning_changed:
        _append_event(
            session,
            application,
            "PLAN_UPDATED",
            note=application.next_action,
        )

    session.commit()
    row = _application_row(session, application_id)
    if row is None:
        raise RuntimeError("Application disappeared after update.")
    return _item(*row)
