from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.enums import Classification, FeedbackReason, JobStatus, WorkMode
from app.db.models import CandidateProfile, ClassificationFeedback, Job, MatchAnalysis
from app.db.session import get_engine, get_session_factory
from app.main import app


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    email_extracted_postings,
                    email_processing_runs,
                    email_attachments,
                    inbound_emails,
                    duplicate_candidates,
                    job_applications,
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


def _job_with_analysis(
    *,
    title: str,
    classification: Classification,
) -> tuple[Job, MatchAnalysis]:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        profile = session.query(CandidateProfile).first()
        if profile is None:
            profile = CandidateProfile(name="Feedback insights profile")
            session.add(profile)
            session.flush()

        job = Job(
            canonical_title=title,
            title_key=title.lower(),
            company_name_raw="Insights Corp",
            company_is_confidential=False,
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(job)
        session.flush()
        analysis = MatchAnalysis(
            job_id=job.id,
            candidate_profile_id=profile.id,
            classification=classification,
            strengths=[],
            gaps=[],
            analyzer_version="feedback-insights-test",
        )
        session.add(analysis)
        session.commit()
        session.refresh(job)
        session.refresh(analysis)
        session.expunge(job)
        session.expunge(analysis)
        return job, analysis


def test_feedback_insights_is_empty_without_feedback() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/feedback/insights")

    assert response.status_code == 200
    assert response.json() == {
        "total_events": 0,
        "jobs_with_feedback": 0,
        "current_overrides": 0,
        "current_agreements": 0,
        "by_reason": [],
        "transitions": [],
    }


def test_feedback_insights_uses_latest_decision_per_job_and_preserves_history_count() -> None:
    first_job, first_analysis = _job_with_analysis(
        title="People Analytics Lead",
        classification=Classification.HIGH_PRIORITY,
    )
    second_job, second_analysis = _job_with_analysis(
        title="HRBP Senior",
        classification=Classification.REVIEW,
    )
    now = datetime.now(UTC)

    with get_session_factory()() as session:
        session.add_all(
            [
                ClassificationFeedback(
                    match_analysis_id=first_analysis.id,
                    job_id=first_job.id,
                    system_classification=Classification.HIGH_PRIORITY,
                    human_classification=Classification.REVIEW,
                    reason_code=FeedbackReason.TITLE,
                    comment="Primera revisión.",
                    created_at=now - timedelta(minutes=2),
                ),
                ClassificationFeedback(
                    match_analysis_id=first_analysis.id,
                    job_id=first_job.id,
                    system_classification=Classification.HIGH_PRIORITY,
                    human_classification=Classification.DISCARD,
                    reason_code=FeedbackReason.SALARY,
                    comment="Decisión vigente.",
                    created_at=now - timedelta(minutes=1),
                ),
                ClassificationFeedback(
                    match_analysis_id=second_analysis.id,
                    job_id=second_job.id,
                    system_classification=Classification.REVIEW,
                    human_classification=Classification.REVIEW,
                    reason_code=FeedbackReason.SKILLS,
                    created_at=now,
                ),
            ]
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/api/v1/feedback/insights")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_events"] == 3
    assert payload["jobs_with_feedback"] == 2
    assert payload["current_overrides"] == 1
    assert payload["current_agreements"] == 1

    reasons = {item["reason"]: item for item in payload["by_reason"]}
    assert set(reasons) == {"SALARY", "SKILLS"}
    assert reasons["SALARY"] == {"reason": "SALARY", "count": 1, "overrides": 1}
    assert reasons["SKILLS"] == {"reason": "SKILLS", "count": 1, "overrides": 0}
    assert "TITLE" not in reasons

    transitions = {
        (item["system_classification"], item["human_classification"]): item["count"]
        for item in payload["transitions"]
    }
    assert transitions[("HIGH_PRIORITY", "DISCARD")] == 1
    assert transitions[("REVIEW", "REVIEW")] == 1
    assert ("HIGH_PRIORITY", "REVIEW") not in transitions
