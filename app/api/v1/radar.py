from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.db.enums import Classification, DuplicateCandidateStatus, JobStatus
from app.db.models import (
    ClassificationFeedback,
    Company,
    DuplicateCandidate,
    Job,
    JobPosting,
    MatchAnalysis,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/radar", tags=["radar"])

RadarView = Literal["high", "review", "discarded", "duplicates"]
SessionDep = Annotated[Session, Depends(get_session)]


class RadarSummary(BaseModel):
    high: int
    review: int
    discarded: int
    duplicates: int


class RadarJobItem(BaseModel):
    id: UUID
    title: str
    company: str | None
    location: str | None
    work_mode: str
    job_status: str
    classification: str | None
    classification_source: str
    score: int | None
    confidence: str | None
    salary_text: str | None
    posting_source: str | None
    source_url: str | None
    last_seen_at: datetime


class RadarJobList(BaseModel):
    items: list[RadarJobItem]
    total: int
    view: RadarView


class RadarPosting(BaseModel):
    source: str | None
    url: str | None
    salary_text: str | None
    published_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime


class RadarAnalysis(BaseModel):
    id: UUID
    score: int | None
    classification: str | None
    confidence: str | None
    strengths: list[object]
    gaps: list[object]
    skill_analysis: dict[str, object]
    rule_results: dict[str, object]
    career_move_assessment: str | None
    salary_assessment: str | None
    recommendation: str | None
    explanation: str | None
    analyzer_version: str
    created_at: datetime


class RadarFeedback(BaseModel):
    id: UUID
    match_analysis_id: UUID
    system_classification: str
    human_classification: str
    reason_code: str
    comment: str | None
    created_at: datetime


class RadarJobDetail(BaseModel):
    id: UUID
    title: str
    company: str | None
    company_is_confidential: bool
    location: str | None
    work_mode: str
    employment_type: str | None
    seniority: str | None
    description: str | None
    job_status: str
    first_seen_at: datetime
    last_seen_at: datetime
    effective_classification: str | None
    classification_source: str
    latest_analysis: RadarAnalysis | None
    latest_feedback: RadarFeedback | None
    postings: list[RadarPosting]


@dataclass(frozen=True)
class RadarReadContext:
    analyses: dict[UUID, MatchAnalysis]
    feedback: dict[UUID, ClassificationFeedback]
    postings: dict[UUID, JobPosting]
    companies: dict[UUID, Company]


def _active_jobs_query() -> Select[tuple[Job]]:
    return select(Job).where(Job.status.in_((JobStatus.ACTIVE, JobStatus.UNKNOWN)))


def _latest_analysis(session: Session, job_id: UUID) -> MatchAnalysis | None:
    return session.scalar(
        select(MatchAnalysis)
        .where(MatchAnalysis.job_id == job_id)
        .order_by(MatchAnalysis.created_at.desc())
        .limit(1)
    )


def _latest_feedback(session: Session, job_id: UUID) -> ClassificationFeedback | None:
    return session.scalar(
        select(ClassificationFeedback)
        .where(ClassificationFeedback.job_id == job_id)
        .order_by(ClassificationFeedback.created_at.desc())
        .limit(1)
    )


def _effective_classification(
    session: Session, job_id: UUID
) -> tuple[Classification | None, str, MatchAnalysis | None]:
    analysis = _latest_analysis(session, job_id)
    feedback = _latest_feedback(session, job_id)
    if feedback is not None:
        return feedback.human_classification, "human", analysis
    if analysis is not None and analysis.classification is not None:
        return analysis.classification, "analysis", analysis
    return None, "unclassified", analysis


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


def _bulk_read_context(session: Session, jobs: list[Job]) -> RadarReadContext:
    job_ids = [job.id for job in jobs]
    if not job_ids:
        return RadarReadContext(analyses={}, feedback={}, postings={}, companies={})

    analyses = {
        analysis.job_id: analysis
        for analysis in session.scalars(
            select(MatchAnalysis)
            .where(MatchAnalysis.job_id.in_(job_ids))
            .distinct(MatchAnalysis.job_id)
            .order_by(MatchAnalysis.job_id, MatchAnalysis.created_at.desc())
        )
    }
    feedback = {
        item.job_id: item
        for item in session.scalars(
            select(ClassificationFeedback)
            .where(ClassificationFeedback.job_id.in_(job_ids))
            .distinct(ClassificationFeedback.job_id)
            .order_by(ClassificationFeedback.job_id, ClassificationFeedback.created_at.desc())
        )
    }
    postings = {
        posting.job_id: posting
        for posting in session.scalars(
            select(JobPosting)
            .where(JobPosting.job_id.in_(job_ids))
            .distinct(JobPosting.job_id)
            .order_by(JobPosting.job_id, JobPosting.last_seen_at.desc())
        )
    }
    company_ids = {job.company_id for job in jobs if job.company_id is not None}
    companies = (
        {
            company.id: company
            for company in session.scalars(select(Company).where(Company.id.in_(company_ids)))
        }
        if company_ids
        else {}
    )
    return RadarReadContext(
        analyses=analyses,
        feedback=feedback,
        postings=postings,
        companies=companies,
    )


def _effective_from_context(
    context: RadarReadContext, job_id: UUID
) -> tuple[Classification | None, str, MatchAnalysis | None]:
    analysis = context.analyses.get(job_id)
    feedback = context.feedback.get(job_id)
    if feedback is not None:
        return feedback.human_classification, "human", analysis
    if analysis is not None and analysis.classification is not None:
        return analysis.classification, "analysis", analysis
    return None, "unclassified", analysis


def _company_name_from_context(context: RadarReadContext, job: Job) -> str | None:
    if job.company_id is not None:
        company = context.companies.get(job.company_id)
        if company is not None:
            return company.name
    return job.company_name_raw


def _safe_posting_url(posting: JobPosting) -> str | None:
    value = posting.canonical_url or posting.source_url_raw
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def _matches_view(classification: Classification | None, view: RadarView) -> bool:
    if view == "high":
        return classification == Classification.HIGH_PRIORITY
    if view == "review":
        return classification in (None, Classification.REVIEW)
    if view == "discarded":
        return classification == Classification.DISCARD
    # Possible duplicates are served as pairs by /api/v1/radar/duplicates.
    return False


def _item_from_context(context: RadarReadContext, job: Job) -> RadarJobItem:
    classification, source, analysis = _effective_from_context(context, job.id)
    posting = context.postings.get(job.id)
    return RadarJobItem(
        id=job.id,
        title=job.canonical_title or (posting.title_raw if posting else None) or "Sin título",
        company=_company_name_from_context(context, job),
        location=job.location_text or (posting.location_raw if posting else None),
        work_mode=job.work_mode.value,
        job_status=job.status.value,
        classification=classification.value if classification is not None else None,
        classification_source=source,
        score=analysis.overall_score if analysis is not None else None,
        confidence=analysis.confidence.value if analysis and analysis.confidence else None,
        salary_text=posting.salary_text if posting is not None else None,
        posting_source=posting.posting_source if posting is not None else None,
        source_url=_safe_posting_url(posting) if posting is not None else None,
        last_seen_at=job.last_seen_at,
    )


@router.get("/summary", response_model=RadarSummary)
def radar_summary(session: SessionDep) -> RadarSummary:
    jobs = list(session.scalars(_active_jobs_query()))
    context = _bulk_read_context(session, jobs)
    high = 0
    review = 0
    discarded = 0
    for job in jobs:
        classification, _, _ = _effective_from_context(context, job.id)
        if classification == Classification.HIGH_PRIORITY:
            high += 1
        elif classification == Classification.DISCARD:
            discarded += 1
        else:
            review += 1

    duplicates = session.scalar(
        select(func.count(DuplicateCandidate.id)).where(
            DuplicateCandidate.status == DuplicateCandidateStatus.PENDING
        )
    ) or 0
    return RadarSummary(
        high=high,
        review=review,
        discarded=discarded,
        duplicates=int(duplicates),
    )


@router.get("/jobs", response_model=RadarJobList)
def list_radar_jobs(
    session: SessionDep,
    view: RadarView = "high",
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
) -> RadarJobList:
    query = _active_jobs_query().order_by(Job.last_seen_at.desc())
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        normalized_company_match = Job.company_id.in_(
            select(Company.id).where(Company.name.ilike(pattern))
        )
        source_posting_match = Job.id.in_(
            select(JobPosting.job_id).where(
                or_(
                    JobPosting.title_raw.ilike(pattern),
                    JobPosting.company_raw.ilike(pattern),
                    JobPosting.location_raw.ilike(pattern),
                )
            )
        )
        query = query.where(
            or_(
                Job.canonical_title.ilike(pattern),
                Job.company_name_raw.ilike(pattern),
                Job.location_text.ilike(pattern),
                normalized_company_match,
                source_posting_match,
            )
        )

    jobs = list(session.scalars(query))
    context = _bulk_read_context(session, jobs)
    matched_jobs = [
        job
        for job in jobs
        if _matches_view(_effective_from_context(context, job.id)[0], view)
    ]
    return RadarJobList(
        items=[_item_from_context(context, job) for job in matched_jobs[:limit]],
        total=len(matched_jobs),
        view=view,
    )


@router.get("/jobs/{job_id}", response_model=RadarJobDetail)
def get_radar_job(job_id: UUID, session: SessionDep) -> RadarJobDetail:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    classification, source, analysis = _effective_classification(session, job.id)
    feedback = _latest_feedback(session, job.id)
    postings = list(
        session.scalars(
            select(JobPosting)
            .where(JobPosting.job_id == job.id)
            .order_by(JobPosting.last_seen_at.desc())
            .limit(10)
        )
    )

    analysis_payload = None
    if analysis is not None:
        analysis_payload = RadarAnalysis(
            id=analysis.id,
            score=analysis.overall_score,
            classification=analysis.classification.value if analysis.classification else None,
            confidence=analysis.confidence.value if analysis.confidence else None,
            strengths=analysis.strengths,
            gaps=analysis.gaps,
            skill_analysis=analysis.skill_analysis,
            rule_results=analysis.rule_results,
            career_move_assessment=analysis.career_move_assessment,
            salary_assessment=analysis.salary_assessment,
            recommendation=analysis.recommendation,
            explanation=analysis.explanation,
            analyzer_version=analysis.analyzer_version,
            created_at=analysis.created_at,
        )

    feedback_payload = None
    if feedback is not None:
        feedback_payload = RadarFeedback(
            id=feedback.id,
            match_analysis_id=feedback.match_analysis_id,
            system_classification=feedback.system_classification.value,
            human_classification=feedback.human_classification.value,
            reason_code=feedback.reason_code.value,
            comment=feedback.comment,
            created_at=feedback.created_at,
        )

    return RadarJobDetail(
        id=job.id,
        title=job.canonical_title or (postings[0].title_raw if postings else None) or "Sin título",
        company=_company_name(session, job),
        company_is_confidential=job.company_is_confidential,
        location=job.location_text or (postings[0].location_raw if postings else None),
        work_mode=job.work_mode.value,
        employment_type=job.employment_type,
        seniority=job.seniority,
        description=job.description or (postings[0].description_raw if postings else None),
        job_status=job.status.value,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        effective_classification=classification.value if classification else None,
        classification_source=source,
        latest_analysis=analysis_payload,
        latest_feedback=feedback_payload,
        postings=[
            RadarPosting(
                source=posting.posting_source,
                url=_safe_posting_url(posting),
                salary_text=posting.salary_text,
                published_at=posting.published_at,
                first_seen_at=posting.first_seen_at,
                last_seen_at=posting.last_seen_at,
            )
            for posting in postings
        ],
    )
