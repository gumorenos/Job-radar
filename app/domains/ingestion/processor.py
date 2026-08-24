from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.enums import IngestionStatus, JobStatus, PostingStatus, WorkMode
from app.db.models import Company, IngestionEvent, Job, JobPosting, PostingSighting
from app.domains.jobs.duplicates import flag_possible_duplicates
from app.domains.jobs.normalization import (
    clean_text,
    comparison_key,
    is_confidential_company,
    normalize_url,
    normalize_work_mode,
    parse_datetime,
)


@dataclass(frozen=True)
class NormalizationResult:
    posting_id: UUID
    analysis_required: bool


def _job_payload(event: IngestionEvent) -> dict[str, Any]:
    raw_job = event.raw_payload.get("job")
    return raw_job if isinstance(raw_job, dict) else {}


def _decimal_amount(value: object | None) -> Decimal | None:
    if value is None or isinstance(value, (bool, dict, list)):
        return None
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _string_list(value: object | None) -> list[str]:
    values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = clean_text(raw)
        if item is None:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item[:200])
    return cleaned


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
    country: str | None,
    city: str | None,
    work_mode_value: object | None,
    employment_type: str | None,
    seniority: str | None,
    required_experience_years: Decimal | None,
    required_degrees: list[str],
    required_skills: list[str],
    seen_at: datetime,
) -> tuple[Job, bool]:
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
        if not existing.country and country:
            existing.country = country
        if not existing.city and city:
            existing.city = city
        if not existing.seniority and seniority:
            existing.seniority = seniority
        if existing.required_experience_years is None and required_experience_years is not None:
            existing.required_experience_years = required_experience_years
        if not existing.required_degrees and required_degrees:
            existing.required_degrees = required_degrees
        if not existing.required_skills and required_skills:
            existing.required_skills = required_skills
        return existing, False

    job = Job(
        canonical_title=canonical_title,
        title_key=title_key,
        company_id=company.id if company else None,
        company_name_raw=company_raw,
        company_is_confidential=company_is_confidential,
        description=description,
        location_text=location,
        country=country,
        city=city,
        work_mode=normalize_work_mode(work_mode_value),
        employment_type=employment_type,
        seniority=seniority,
        required_experience_years=required_experience_years,
        required_degrees=required_degrees,
        required_skills=required_skills,
        status=JobStatus.ACTIVE,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        parent_job_id=previous.id if previous is not None else None,
    )
    session.add(job)
    session.flush()
    return job, True


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


def _update_existing_posting(
    session: Session,
    posting: JobPosting,
    *,
    title: str | None,
    company_raw: str | None,
    location: str | None,
    country: str | None,
    city: str | None,
    description: str | None,
    work_mode_value: object | None,
    employment_type: str | None,
    seniority: str | None,
    required_experience_years: Decimal | None,
    required_degrees: list[str],
    required_skills: list[str],
    salary_text: str | None,
    salary_min: Decimal | None,
    salary_max: Decimal | None,
    currency: str | None,
    salary_period: str | None,
    source_url_raw: str | None,
    normalized_url: str | None,
    published_at: datetime | None,
    seen_at: datetime,
) -> bool:
    """Refresh a rediscovered posting and report whether matching inputs changed."""

    job = session.get(Job, posting.job_id)
    if job is None:
        raise LookupError(f"Job {posting.job_id} does not exist for posting {posting.id}.")

    material_change = False
    posting.last_seen_at = seen_at
    job.last_seen_at = seen_at

    if title is not None and title != posting.title_raw:
        posting.title_raw = title
        if title != job.canonical_title:
            job.canonical_title = title
            job.title_key = comparison_key(title)
            material_change = True

    if company_raw is not None and company_raw != posting.company_raw:
        posting.company_raw = company_raw
        company, confidential = _company_for(session, company_raw)
        new_company_id = company.id if company is not None else None
        if (
            new_company_id != job.company_id
            or company_raw != job.company_name_raw
            or confidential != job.company_is_confidential
        ):
            job.company_id = new_company_id
            job.company_name_raw = company_raw
            job.company_is_confidential = confidential
            material_change = True

    if location is not None and location != posting.location_raw:
        posting.location_raw = location
        if location != job.location_text:
            job.location_text = location
            material_change = True

    if country is not None and country != job.country:
        job.country = country
        material_change = True
    if city is not None and city != job.city:
        job.city = city
        material_change = True
    if description is not None and description != posting.description_raw:
        posting.description_raw = description
        if description != job.description:
            job.description = description
            material_change = True
    if employment_type is not None and employment_type != job.employment_type:
        job.employment_type = employment_type
        material_change = True
    if seniority is not None and seniority != job.seniority:
        job.seniority = seniority
        material_change = True
    if (
        required_experience_years is not None
        and required_experience_years != job.required_experience_years
    ):
        job.required_experience_years = required_experience_years
        material_change = True
    if required_degrees and required_degrees != job.required_degrees:
        job.required_degrees = required_degrees
        material_change = True
    if required_skills and required_skills != job.required_skills:
        job.required_skills = required_skills
        material_change = True

    if work_mode_value is not None:
        work_mode = normalize_work_mode(work_mode_value)
        if work_mode != WorkMode.UNKNOWN and work_mode != job.work_mode:
            job.work_mode = work_mode
            material_change = True

    if salary_text is not None and salary_text != posting.salary_text:
        posting.salary_text = salary_text
        material_change = True
    if salary_min is not None and salary_min != posting.salary_min:
        posting.salary_min = salary_min
        material_change = True
    if salary_max is not None and salary_max != posting.salary_max:
        posting.salary_max = salary_max
        material_change = True
    if currency is not None and currency != posting.currency:
        posting.currency = currency
        material_change = True
    if salary_period is not None and salary_period != posting.salary_period:
        posting.salary_period = salary_period
        material_change = True

    if source_url_raw is not None:
        posting.source_url_raw = source_url_raw
    if normalized_url is not None:
        posting.source_url_normalized = normalized_url
        posting.canonical_url = normalized_url
    if published_at is not None:
        posting.published_at = published_at

    return material_change


def normalize_ingestion_event(session: Session, event_id: UUID) -> NormalizationResult:
    event = session.get(IngestionEvent, event_id)
    if event is None:
        raise LookupError(f"Ingestion event {event_id} does not exist.")

    event.status = IngestionStatus.PROCESSING
    raw_job = _job_payload(event)

    title = clean_text(raw_job.get("title"))
    company_raw = clean_text(raw_job.get("company"))
    location = clean_text(raw_job.get("location"))
    country = clean_text(raw_job.get("country"))
    city = clean_text(raw_job.get("city"))
    description = clean_text(raw_job.get("description"))
    work_mode_value = raw_job.get("work_mode") or raw_job.get("modality") or raw_job.get("remote")
    employment_type = clean_text(raw_job.get("employment_type"))
    seniority = clean_text(raw_job.get("seniority"))
    required_experience_years = _decimal_amount(raw_job.get("required_experience_years"))
    required_degrees = _string_list(raw_job.get("required_degrees"))
    required_skills = _string_list(raw_job.get("required_skills"))
    salary_text = clean_text(raw_job.get("salary_text"))
    salary_min = _decimal_amount(raw_job.get("salary_min"))
    salary_max = _decimal_amount(raw_job.get("salary_max"))
    currency_value = clean_text(raw_job.get("currency"))
    currency = currency_value.upper() if currency_value else None
    salary_period = clean_text(raw_job.get("salary_period"))
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
        analysis_required = _update_existing_posting(
            session,
            posting,
            title=title,
            company_raw=company_raw,
            location=location,
            country=country,
            city=city,
            description=description,
            work_mode_value=work_mode_value,
            employment_type=employment_type,
            seniority=seniority,
            required_experience_years=required_experience_years,
            required_degrees=required_degrees,
            required_skills=required_skills,
            salary_text=salary_text,
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            salary_period=salary_period,
            source_url_raw=source_url_raw,
            normalized_url=normalized_url,
            published_at=published_at,
            seen_at=event.received_at,
        )
        _record_sighting(session, event, posting)
        event.status = IngestionStatus.COMPLETED
        event.processed_at = datetime.now(UTC)
        return NormalizationResult(posting_id=posting.id, analysis_required=analysis_required)

    company, is_confidential = _company_for(session, company_raw)
    job, job_created = _job_for(
        session,
        canonical_title=title,
        company=company,
        company_raw=company_raw,
        company_is_confidential=is_confidential,
        description=description,
        location=location,
        country=country,
        city=city,
        work_mode_value=work_mode_value,
        employment_type=employment_type,
        seniority=seniority,
        required_experience_years=required_experience_years,
        required_degrees=required_degrees,
        required_skills=required_skills,
        seen_at=event.received_at,
    )
    if job_created:
        flag_possible_duplicates(session, job, seen_at=event.received_at)

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
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        salary_period=salary_period,
        published_at=published_at,
        first_seen_at=event.received_at,
        last_seen_at=event.received_at,
        posting_status=PostingStatus.ACTIVE,
    )
    session.add(posting)
    session.flush()
    _record_sighting(session, event, posting)

    event.status = IngestionStatus.COMPLETED
    event.processed_at = datetime.now(UTC)
    return NormalizationResult(posting_id=posting.id, analysis_required=True)
