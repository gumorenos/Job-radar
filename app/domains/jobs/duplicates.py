from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.enums import ApplicationStage, DuplicateCandidateStatus, JobStatus
from app.db.models import (
    ClassificationFeedback,
    DuplicateCandidate,
    Job,
    JobApplication,
    JobPosting,
    MatchAnalysis,
    Notification,
)
from app.domains.jobs.normalization import comparison_key

_STAGE_RANK = {
    ApplicationStage.TO_APPLY: 0,
    ApplicationStage.APPLIED: 1,
    ApplicationStage.INTERVIEW: 2,
    ApplicationStage.OFFER: 3,
    ApplicationStage.CLOSED: 4,
}


def _similarity(left: str | None, right: str | None) -> float:
    left_key = comparison_key(left)
    right_key = comparison_key(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def _company_similarity(left: Job, right: Job) -> float:
    if left.company_id is not None and left.company_id == right.company_id:
        return 1.0
    return _similarity(left.company_name_raw, right.company_name_raw)


def _location_similarity(left: Job, right: Job) -> float:
    left_key = comparison_key(left.location_text)
    right_key = comparison_key(right.location_text)
    if not left_key or not right_key:
        return 0.5
    if left_key == right_key:
        return 1.0
    if left_key in right_key or right_key in left_key:
        return 0.85
    return SequenceMatcher(None, left_key, right_key).ratio()


def _pair(left: UUID, right: UUID) -> tuple[UUID, UUID]:
    return (left, right) if str(left) < str(right) else (right, left)


def flag_possible_duplicates(
    session: Session,
    job: Job,
    *,
    seen_at: datetime | None = None,
) -> list[DuplicateCandidate]:
    """Persist uncertain duplicate candidates without auto-merging them."""

    if not job.title_key:
        return []
    current = seen_at or datetime.now(UTC)
    cutoff = current - timedelta(days=get_settings().reappearance_window_days)
    candidates = list(
        session.scalars(
            select(Job)
            .where(
                Job.id != job.id,
                Job.status.in_((JobStatus.ACTIVE, JobStatus.UNKNOWN)),
                Job.last_seen_at >= cutoff,
            )
            .order_by(Job.last_seen_at.desc())
            .limit(200)
        )
    )

    created: list[DuplicateCandidate] = []
    for other in candidates:
        if job.parent_job_id == other.id or other.parent_job_id == job.id:
            continue

        title_similarity = _similarity(job.canonical_title, other.canonical_title)
        company_similarity = _company_similarity(job, other)
        location_similarity = _location_similarity(job, other)
        same_company = company_similarity >= 0.98
        plausible = (same_company and title_similarity >= 0.72) or (
            title_similarity >= 0.90 and company_similarity >= 0.82
        )
        if not plausible:
            continue

        confidence = (
            title_similarity * 0.65
            + company_similarity * 0.25
            + location_similarity * 0.10
        )
        if confidence < 0.78:
            continue

        job_a_id, job_b_id = _pair(job.id, other.id)
        existing = session.scalar(
            select(DuplicateCandidate.id).where(
                DuplicateCandidate.job_a_id == job_a_id,
                DuplicateCandidate.job_b_id == job_b_id,
            )
        )
        if existing is not None:
            continue

        candidate = DuplicateCandidate(
            job_a_id=job_a_id,
            job_b_id=job_b_id,
            confidence=Decimal(f"{min(confidence, 0.99):.4f}"),
            reasons={
                "title_similarity": round(title_similarity, 4),
                "company_similarity": round(company_similarity, 4),
                "location_similarity": round(location_similarity, 4),
                "same_company": same_company,
            },
            status=DuplicateCandidateStatus.PENDING,
        )
        session.add(candidate)
        created.append(candidate)

    if created:
        session.flush()
    return created


def keep_separate(candidate: DuplicateCandidate, *, now: datetime | None = None) -> None:
    candidate.status = DuplicateCandidateStatus.KEPT_SEPARATE
    candidate.resolved_at = now or datetime.now(UTC)
    candidate.resolved_survivor_job_id = None


def _merge_application(session: Session, survivor: Job, duplicate: Job) -> None:
    survivor_application = session.scalar(
        select(JobApplication).where(JobApplication.job_id == survivor.id)
    )
    duplicate_application = session.scalar(
        select(JobApplication).where(JobApplication.job_id == duplicate.id)
    )
    if duplicate_application is None:
        return
    if survivor_application is None:
        duplicate_application.job_id = survivor.id
        return

    if _STAGE_RANK[duplicate_application.stage] > _STAGE_RANK[survivor_application.stage]:
        survivor_application.stage = duplicate_application.stage
    applied_dates = [
        value
        for value in (survivor_application.applied_at, duplicate_application.applied_at)
        if value is not None
    ]
    survivor_application.applied_at = min(applied_dates) if applied_dates else None
    if survivor_application.stage == ApplicationStage.CLOSED:
        closed_dates = [
            value
            for value in (survivor_application.closed_at, duplicate_application.closed_at)
            if value is not None
        ]
        survivor_application.closed_at = max(closed_dates) if closed_dates else datetime.now(UTC)
    else:
        survivor_application.closed_at = None

    notes = [
        value.strip()
        for value in (survivor_application.notes, duplicate_application.notes)
        if value and value.strip()
    ]
    survivor_application.notes = "\n\n".join(dict.fromkeys(notes)) or None
    session.delete(duplicate_application)


def _remap_related_candidates(
    session: Session,
    duplicate_id: UUID,
    survivor_id: UUID,
    current_candidate_id: UUID,
    resolved_at: datetime,
) -> None:
    related = list(
        session.scalars(
            select(DuplicateCandidate).where(
                DuplicateCandidate.id != current_candidate_id,
                DuplicateCandidate.status == DuplicateCandidateStatus.PENDING,
                or_(
                    DuplicateCandidate.job_a_id == duplicate_id,
                    DuplicateCandidate.job_b_id == duplicate_id,
                ),
            )
        )
    )
    for candidate in related:
        other_id = (
            candidate.job_b_id if candidate.job_a_id == duplicate_id else candidate.job_a_id
        )
        if other_id == survivor_id:
            candidate.status = DuplicateCandidateStatus.MERGED
            candidate.resolved_survivor_job_id = survivor_id
            candidate.resolved_at = resolved_at
            continue

        job_a_id, job_b_id = _pair(survivor_id, other_id)
        existing = session.scalar(
            select(DuplicateCandidate.id).where(
                DuplicateCandidate.id != candidate.id,
                DuplicateCandidate.job_a_id == job_a_id,
                DuplicateCandidate.job_b_id == job_b_id,
            )
        )
        if existing is not None:
            candidate.status = DuplicateCandidateStatus.MERGED
            candidate.resolved_survivor_job_id = survivor_id
            candidate.resolved_at = resolved_at
        else:
            candidate.job_a_id = job_a_id
            candidate.job_b_id = job_b_id


def merge_duplicate_candidate(
    session: Session,
    candidate: DuplicateCandidate,
    survivor_job_id: UUID,
    *,
    now: datetime | None = None,
) -> Job:
    if candidate.status != DuplicateCandidateStatus.PENDING:
        raise ValueError("Duplicate candidate has already been resolved.")
    if survivor_job_id not in {candidate.job_a_id, candidate.job_b_id}:
        raise ValueError("Survivor job must belong to the duplicate candidate pair.")

    duplicate_job_id = (
        candidate.job_b_id if survivor_job_id == candidate.job_a_id else candidate.job_a_id
    )
    survivor = session.get(Job, survivor_job_id)
    duplicate = session.get(Job, duplicate_job_id)
    if survivor is None or duplicate is None:
        raise LookupError("One of the duplicate jobs no longer exists.")

    resolved_at = now or datetime.now(UTC)
    _merge_application(session, survivor, duplicate)

    session.execute(
        update(JobPosting).where(JobPosting.job_id == duplicate.id).values(job_id=survivor.id)
    )
    session.execute(
        update(MatchAnalysis).where(MatchAnalysis.job_id == duplicate.id).values(job_id=survivor.id)
    )
    session.execute(
        update(ClassificationFeedback)
        .where(ClassificationFeedback.job_id == duplicate.id)
        .values(job_id=survivor.id)
    )
    session.execute(
        update(Notification).where(Notification.job_id == duplicate.id).values(job_id=survivor.id)
    )

    children = list(
        session.scalars(select(Job).where(Job.parent_job_id == duplicate.id, Job.id != survivor.id))
    )
    for child in children:
        child.parent_job_id = survivor.id
    if survivor.parent_job_id == duplicate.id:
        parent_id = duplicate.parent_job_id
        survivor.parent_job_id = parent_id if parent_id != survivor.id else None

    survivor.first_seen_at = min(survivor.first_seen_at, duplicate.first_seen_at)
    survivor.last_seen_at = max(survivor.last_seen_at, duplicate.last_seen_at)
    if not survivor.description and duplicate.description:
        survivor.description = duplicate.description
    if not survivor.location_text and duplicate.location_text:
        survivor.location_text = duplicate.location_text
    if not survivor.country and duplicate.country:
        survivor.country = duplicate.country
    if not survivor.city and duplicate.city:
        survivor.city = duplicate.city

    _remap_related_candidates(
        session,
        duplicate.id,
        survivor.id,
        candidate.id,
        resolved_at,
    )
    candidate.status = DuplicateCandidateStatus.MERGED
    candidate.resolved_survivor_job_id = survivor.id
    candidate.resolved_at = resolved_at

    duplicate.status = JobStatus.CLOSED
    duplicate.closed_at = resolved_at
    duplicate.parent_job_id = survivor.id
    session.flush()
    return survivor
