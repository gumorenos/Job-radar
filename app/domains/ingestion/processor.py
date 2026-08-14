from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.enums import IngestionStatus, JobStatus, PostingStatus
from app.db.models import Company, IngestionEvent, Job, JobPosting, PostingSighting
from app.domains.jobs.normalization import (
    clean_text,
    comparison_key,
    is_confidential_company,
    normalize_url,
    normalize_work_mode,
    parse_datetime,
)


def _job_payload(event: IngestionEvent) -> dict[str, Any]:
    raw_job = event.raw_payload.get("job")
    return raw_job if isinstance(raw_job, dict) else {}


def _find_existing_posting(
    session: Session,
    posting_source: str | None,
    source_external_id: str | None,
    normalized_url: str | None,
) -> JobPosting | None:
    if posting_source and source_external_id:
        posting = session.scalar(
            select(JobPosting).where(
                JobPosting.posting_source == posting_source,
                JobPosting.source_external_id == source_external_id,
            )
        )
        if posting is not None:
            return posting

    if normalized_url:
        return session.scalar(
            select(JobPosting)
            .where(JobPosting.source_url_normalized == normalized_url)
            .order_by(JobPosting.last_seen_at.desc())
            .limit(1)
        )
    return None


def _company_for(
    session: Session,
    company_raw: str | None,
) -> tuple[Company | None, bool]:
    if is_confidential_company(company_raw):
        return None, True

    normalized = comparison_key(company_raw)
    if normalized is None or company_raw is None:
        return None, False

    company = session.scalar(select(Company).where(Company.normalized_name == normalized))
    if company is None:
        company = Company(name=company_raw, normalized_name=normalized)
        session.add(company)
        session.flush()
    return company, False


def _job_for(
    session: Session,
    *,
    canonical_title: str | None,
    company: Company | None,
    company_raw: str | None,
    company_is_confidential: bool,
    description: str | None,
    location: str | None,
    work_mode_value: object | None,
    employment_type: str | None,
    seen_at: datetime,
) -> Job:
    settings = get_settings()
    title_key = comparison_key(canonical_title)
    existing: Job | None = None
    previous: Job | None = None

    if company is not None and title_key is not None:
        same_role_jobs = list(
            session.scalars(
                select(Job)
                .where(
                    Job.company_id == company.id,
                    Job.title_key == title_key,
                )
                .order_by(Job.last_seen_at.desc())
            )
        )
        previous = same_role_jobs[0] if same_role_jobs else None
        cutoff = seen_at - timedelta(days=settings.reappearance_window_days)
        location_key = comparison_key(location)
        for candidate in same_role_jobs:
            if candidate.last_seen_at < cutoff:
                continue
            if candidate.status not in (JobStatus.ACTIVE, JobStatus.UNKNOWN):
                continue
            candidate_location_key = comparison_key(candidate.location_text)
            if location_key and candidate_location_key and location_key != candidate_location_key:
                continue
            existing = candidate
            break

    if existing is not None:
        existing.last_seen_at = seen_at
        if not existing.description and description:
            existing.description = description
        if not existing.location_text and location:
            existing.location_text = location
        return existing

    job = Job(
        canonical_title=canonical_title,
        title_key=title_key,
        company_id=company.id if company else None,
        company_name_raw=company_raw,
        company_is_confidential=company_is_confidential,
        description=description,
        location_text=location,
        work_mode=normalize_work_mode(work_mode_value),
        employment_type=employment_type,
        status=JobStatus.ACTIVE,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        parent_job_id=previous.id if previous is not None else None,
    )
    session.add(job)
    session.flush()
    return job


def _record_sighting(session: Session, event: IngestionEvent, posting: JobPosting) -> None:
    exists = session.scalar(
        select(PostingSighting.id).where(
            PostingSighting.ingestion_event_id == event.id,
            PostingSighting.job_posting_id == posting.id,
        )
    )
    if exists is None:
        session.add(
            PostingSighting(
                ingestion_event_id=event.id,
                job_posting_id=posting.id,
                seen_at=event.received_at,
            )
        )


def normalize_ingestion_event(session: Session, event_id: UUID) -> UUID:
    event = session.get(IngestionEvent, event_id)
    if event is None:
        raise LookupError(f"Ingestion event {event_id} does not exist.")

    event.status = IngestionStatus.PROCESSING
    raw_job = _job_payload(event)

    title = clean_text(raw_job.get("title"))
    company_raw = clean_text(raw_job.get("company"))
    location = clean_text(raw_job.get("location"))
    description = clean_text(raw_job.get("description"))
    work_mode_value = raw_job.get("work_mode") or raw_job.get("modality") or raw_job.get("remote")
    employment_type = clean_text(raw_job.get("employment_type"))
    salary_text = clean_text(raw_job.get("salary_text"))
    source_url_raw = clean_text(raw_job.get("url"))
    normalized_url = normalize_url(source_url_raw)
    published_at = parse_datetime(raw_job.get("published_at"))
    posting_source = clean_text(event.posting_source)
    source_external_id = clean_text(event.external_id)

    posting = _find_existing_posting(
        session,
        posting_source=posting_source,
        source_external_id=source_external_id,
        normalized_url=normalized_url,
    )
    if posting is not None:
        posting.last_seen_at = event.received_at
        posting_job = session.get(Job, posting.job_id)
        if posting_job is not None:
            posting_job.last_seen_at = event.received_at
        _record_sighting(session, event, posting)
        event.status = IngestionStatus.COMPLETED
        event.processed_at = datetime.now(timezone.utc)
        return posting.id

    company, is_confidential = _company_for(session, company_raw)
    job = _job_for(
        session,
        canonical_title=title,
        company=company,
        company_raw=company_raw,
        company_is_confidential=is_confidential,
        description=description,
        location=location,
        work_mode_value=work_mode_value,
        employment_type=employment_type,
        seen_at=event.received_at,
    )

    posting = JobPosting(
        job_id=job.id,
        posting_source=posting_source,
        source_external_id=source_external_id,
        source_url_raw=source_url_raw,
        source_url_normalized=normalized_url,
        canonical_url=normalized_url,
        title_raw=title,
        company_raw=company_raw,
        location_raw=location,
        description_raw=description,
        salary_text=salary_text,
        published_at=published_at,
        first_seen_at=event.received_at,
        last_seen_at=event.received_at,
        posting_status=PostingStatus.ACTIVE,
    )
    session.add(posting)
    session.flush()
    _record_sighting(session, event, posting)

    event.status = IngestionStatus.COMPLETED
    event.processed_at = datetime.now(timezone.utc)
    return posting.id
