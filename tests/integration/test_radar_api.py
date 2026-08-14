from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.enums import (
    Classification,
    Confidence,
    FeedbackReason,
    JobStatus,
    PostingStatus,
    WorkMode,
)
from app.db.models import (
    CandidateProfile,
    ClassificationFeedback,
    Company,
    Job,
    JobPosting,
    MatchAnalysis,
)
from app.db.session import get_engine, get_session_factory
from app.main import app


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    classification_feedback,
                    notifications,
                    match_analyses,
                    posting_sightings,
                    job_postings,
                    processing_tasks,
                    ingestion_events,
                    jobs,
                    cv_versions,
                    companies,
                    candidate_profiles
                CASCADE
                """
            )
        )


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None]:
    _truncate_database()
    yield
    _truncate_database()


def _create_job(title: str, company_name: str, url: str) -> Job:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        company = Company(name=company_name, normalized_name=company_name.lower())
        session.add(company)
        session.flush()
        job = Job(
            canonical_title=title,
            title_key=title.lower(),
            company_id=company.id,
            company_name_raw=company_name,
            company_is_confidential=False,
            description=f"Description for {title}",
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(job)
        session.flush()
        session.add(
            JobPosting(
                job_id=job.id,
                posting_source="linkedin",
                source_url_raw=url,
                source_url_normalized=url,
                canonical_url=url,
                title_raw=title,
                company_raw=company_name,
                location_raw="Lima",
                description_raw=f"Description for {title}",
                salary_text="S/ 8,500",
                first_seen_at=now,
                last_seen_at=now,
                posting_status=PostingStatus.ACTIVE,
            )
        )
        session.commit()
        return job


def test_unanalysed_jobs_are_visible_in_review_and_detail() -> None:
    job = _create_job("HR Business Partner", "Example Corp", "https://example.com/jobs/1")

    with TestClient(app) as client:
        summary = client.get("/api/v1/radar/summary")
        jobs = client.get("/api/v1/radar/jobs?view=review")
        detail = client.get(f"/api/v1/radar/jobs/{job.id}")

    assert summary.status_code == 200
    assert summary.json() == {"high": 0, "review": 1, "discarded": 0, "duplicates": 0}

    assert jobs.status_code == 200
    payload = jobs.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "HR Business Partner"
    assert payload["items"][0]["classification"] is None
    assert payload["items"][0]["classification_source"] == "unclassified"
    assert payload["items"][0]["salary_text"] == "S/ 8,500"

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["company"] == "Example Corp"
    assert detail_payload["description"] == "Description for HR Business Partner"
    assert detail_payload["latest_analysis"] is None
    assert detail_payload["postings"][0]["url"] == "https://example.com/jobs/1"


def test_human_feedback_overrides_system_classification_in_radar() -> None:
    high_job = _create_job("People Analytics Lead", "Analytics Corp", "https://example.com/jobs/2")
    corrected_job = _create_job("Strategic HRBP", "HR Corp", "https://example.com/jobs/3")

    with get_session_factory()() as session:
        profile = CandidateProfile(name="QA profile")
        session.add(profile)
        session.flush()

        high_analysis = MatchAnalysis(
            job_id=high_job.id,
            candidate_profile_id=profile.id,
            overall_score=91,
            classification=Classification.HIGH_PRIORITY,
            confidence=Confidence.HIGH,
            strengths=["People Analytics"],
            gaps=[],
            analyzer_version="qa-v1",
        )
        corrected_analysis = MatchAnalysis(
            job_id=corrected_job.id,
            candidate_profile_id=profile.id,
            overall_score=88,
            classification=Classification.HIGH_PRIORITY,
            confidence=Confidence.HIGH,
            strengths=["HRBP"],
            gaps=[],
            analyzer_version="qa-v1",
        )
        session.add_all([high_analysis, corrected_analysis])
        session.flush()
        session.add(
            ClassificationFeedback(
                match_analysis_id=corrected_analysis.id,
                job_id=corrected_job.id,
                system_classification=Classification.HIGH_PRIORITY,
                human_classification=Classification.REVIEW,
                reason_code=FeedbackReason.TITLE,
                comment="Needs a closer look.",
            )
        )
        session.commit()

    with TestClient(app) as client:
        summary = client.get("/api/v1/radar/summary")
        high = client.get("/api/v1/radar/jobs?view=high")
        review = client.get("/api/v1/radar/jobs?view=review")
        corrected_detail = client.get(f"/api/v1/radar/jobs/{corrected_job.id}")

    assert summary.json() == {"high": 1, "review": 1, "discarded": 0, "duplicates": 0}
    assert high.json()["items"][0]["id"] == str(high_job.id)
    assert high.json()["items"][0]["score"] == 91
    assert review.json()["items"][0]["id"] == str(corrected_job.id)
    assert review.json()["items"][0]["classification"] == "REVIEW"
    assert review.json()["items"][0]["classification_source"] == "human"
    assert corrected_detail.json()["effective_classification"] == "REVIEW"
    assert corrected_detail.json()["classification_source"] == "human"
    assert corrected_detail.json()["latest_analysis"]["classification"] == "HIGH_PRIORITY"
