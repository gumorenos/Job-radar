from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.enums import DuplicateCandidateStatus
from app.db.models import Company, DuplicateCandidate, Job, JobPosting
from app.db.session import get_session
from app.domains.jobs.duplicates import keep_separate, merge_duplicate_candidate

router = APIRouter(prefix="/api/v1/radar/duplicates", tags=["duplicates"])
SessionDep = Annotated[Session, Depends(get_session)]
DuplicateDecision = Literal["MERGE", "KEEP_SEPARATE"]


class DuplicateJobBrief(BaseModel):
    id: UUID
    title: str
    company: str | None
    location: str | None
    work_mode: str
    description: str | None
    salary_text: str | None
    first_seen_at: datetime
    last_seen_at: datetime


class DuplicateCandidateItem(BaseModel):
    id: UUID
    confidence: Decimal
    reasons: dict[str, object]
    status: DuplicateCandidateStatus
    job_a: DuplicateJobBrief
    job_b: DuplicateJobBrief
    resolved_survivor_job_id: UUID | None
    resolved_at: datetime | None
    created_at: datetime


class DuplicateCandidateList(BaseModel):
    items: list[DuplicateCandidateItem]
    total: int


class DuplicateResolutionRequest(BaseModel):
    decision: DuplicateDecision
    survivor_job_id: UUID | None = None


@dataclass(frozen=True)
class DuplicateReadContext:
    jobs: dict[UUID, Job]
    companies: dict[UUID, Company]
    postings: dict[UUID, JobPosting]


def _company_name(session: Session, job: Job) -> str | None:
    if job.company_id is not None:
        company = session.get(Company, job.company_id)
        if company is not None:
            return company.name
    return job.company_name_raw


def _latest_posting(session: Session, job_id: UUID) -> JobPosting | None:
    return session.scalar(
        select(JobPosting)
        .where(JobPosting.job_id == job_id)
        .order_by(JobPosting.last_seen_at.desc())
        .limit(1)
    )


def _brief(session: Session, job: Job) -> DuplicateJobBrief:
    posting = _latest_posting(session, job.id)
    return DuplicateJobBrief(
        id=job.id,
        title=job.canonical_title or (posting.title_raw if posting else None) or "Sin título",
        company=_company_name(session, job),
        location=job.location_text or (posting.location_raw if posting else None),
        work_mode=job.work_mode.value,
        description=job.description or (posting.description_raw if posting else None),
        salary_text=posting.salary_text if posting is not None else None,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
    )


def _item(session: Session, candidate: DuplicateCandidate) -> DuplicateCandidateItem:
    job_a = session.get(Job, candidate.job_a_id)
    job_b = session.get(Job, candidate.job_b_id)
    if job_a is None or job_b is None:
        raise LookupError("A duplicate candidate references a missing job.")
    return DuplicateCandidateItem(
        id=candidate.id,
        confidence=candidate.confidence,
        reasons=candidate.reasons,
        status=candidate.status,
        job_a=_brief(session, job_a),
        job_b=_brief(session, job_b),
        resolved_survivor_job_id=candidate.resolved_survivor_job_id,
        resolved_at=candidate.resolved_at,
        created_at=candidate.created_at,
    )


def _bulk_read_context(
    session: Session, candidates: list[DuplicateCandidate]
) -> DuplicateReadContext:
    job_ids = {
        job_id
        for candidate in candidates
        for job_id in (candidate.job_a_id, candidate.job_b_id)
    }
    if not job_ids:
        return DuplicateReadContext(jobs={}, companies={}, postings={})

    jobs = {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(job_ids)))}
    company_ids = {job.company_id for job in jobs.values() if job.company_id is not None}
    companies = (
        {
            company.id: company
            for company in session.scalars(select(Company).where(Company.id.in_(company_ids)))
        }
        if company_ids
        else {}
    )
    postings = {
        posting.job_id: posting
        for posting in session.scalars(
            select(JobPosting)
            .where(JobPosting.job_id.in_(job_ids))
            .distinct(JobPosting.job_id)
            .order_by(JobPosting.job_id, JobPosting.last_seen_at.desc())
        )
    }
    return DuplicateReadContext(jobs=jobs, companies=companies, postings=postings)


def _company_name_from_context(context: DuplicateReadContext, job: Job) -> str | None:
    if job.company_id is not None:
        company = context.companies.get(job.company_id)
        if company is not None:
            return company.name
    return job.company_name_raw


def _brief_from_context(context: DuplicateReadContext, job: Job) -> DuplicateJobBrief:
    posting = context.postings.get(job.id)
    return DuplicateJobBrief(
        id=job.id,
        title=job.canonical_title or (posting.title_raw if posting else None) or "Sin título",
        company=_company_name_from_context(context, job),
        location=job.location_text or (posting.location_raw if posting else None),
        work_mode=job.work_mode.value,
        description=job.description or (posting.description_raw if posting else None),
        salary_text=posting.salary_text if posting is not None else None,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
    )


def _item_from_context(
    context: DuplicateReadContext, candidate: DuplicateCandidate
) -> DuplicateCandidateItem:
    job_a = context.jobs.get(candidate.job_a_id)
    job_b = context.jobs.get(candidate.job_b_id)
    if job_a is None or job_b is None:
        raise LookupError("A duplicate candidate references a missing job.")
    return DuplicateCandidateItem(
        id=candidate.id,
        confidence=candidate.confidence,
        reasons=candidate.reasons,
        status=candidate.status,
        job_a=_brief_from_context(context, job_a),
        job_b=_brief_from_context(context, job_b),
        resolved_survivor_job_id=candidate.resolved_survivor_job_id,
        resolved_at=candidate.resolved_at,
        created_at=candidate.created_at,
    )


def _search_condition(job_a: Job, job_b: Job, pattern: str):
    company_ids = select(Company.id).where(Company.name.ilike(pattern))
    posting_job_ids = select(JobPosting.job_id).where(
        or_(
            JobPosting.title_raw.ilike(pattern),
            JobPosting.company_raw.ilike(pattern),
            JobPosting.location_raw.ilike(pattern),
        )
    )
    return or_(
        job_a.canonical_title.ilike(pattern),
        job_a.company_name_raw.ilike(pattern),
        job_a.location_text.ilike(pattern),
        job_a.company_id.in_(company_ids),
        job_a.id.in_(posting_job_ids),
        job_b.canonical_title.ilike(pattern),
        job_b.company_name_raw.ilike(pattern),
        job_b.location_text.ilike(pattern),
        job_b.company_id.in_(company_ids),
        job_b.id.in_(posting_job_ids),
    )


@router.get("", response_model=DuplicateCandidateList)
def list_duplicate_candidates(
    session: SessionDep,
    status: DuplicateCandidateStatus = DuplicateCandidateStatus.PENDING,
    q: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> DuplicateCandidateList:
    job_a = aliased(Job)
    job_b = aliased(Job)
    query = (
        select(DuplicateCandidate)
        .join(job_a, DuplicateCandidate.job_a_id == job_a.id)
        .join(job_b, DuplicateCandidate.job_b_id == job_b.id)
        .where(DuplicateCandidate.status == status)
    )
    count_query = (
        select(func.count(DuplicateCandidate.id))
        .select_from(DuplicateCandidate)
        .join(job_a, DuplicateCandidate.job_a_id == job_a.id)
        .join(job_b, DuplicateCandidate.job_b_id == job_b.id)
        .where(DuplicateCandidate.status == status)
    )

    search = q.strip() if q else ""
    if search:
        condition = _search_condition(job_a, job_b, f"%{search}%")
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = int(session.scalar(count_query) or 0)
    candidates = list(
        session.scalars(
            query.order_by(
                DuplicateCandidate.confidence.desc(),
                DuplicateCandidate.created_at.desc(),
                DuplicateCandidate.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )
    context = _bulk_read_context(session, candidates)
    return DuplicateCandidateList(
        items=[_item_from_context(context, candidate) for candidate in candidates],
        total=total,
    )


@router.post("/{candidate_id}/resolve", response_model=DuplicateCandidateItem)
def resolve_duplicate_candidate(
    candidate_id: UUID,
    payload: DuplicateResolutionRequest,
    session: SessionDep,
) -> DuplicateCandidateItem:
    candidate = session.get(DuplicateCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Duplicate candidate not found.")
    if candidate.status != DuplicateCandidateStatus.PENDING:
        raise HTTPException(status_code=409, detail="Duplicate candidate is already resolved.")

    if payload.decision == "KEEP_SEPARATE":
        keep_separate(candidate)
    else:
        job_a = session.get(Job, candidate.job_a_id)
        job_b = session.get(Job, candidate.job_b_id)
        if job_a is None or job_b is None:
            raise HTTPException(
                status_code=409,
                detail="One of the duplicate jobs no longer exists.",
            )
        survivor_id = payload.survivor_job_id
        if survivor_id is None:
            survivor_id = job_a.id if job_a.first_seen_at <= job_b.first_seen_at else job_b.id
        try:
            merge_duplicate_candidate(session, candidate, survivor_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    session.commit()
    session.refresh(candidate)
    return _item(session, candidate)
