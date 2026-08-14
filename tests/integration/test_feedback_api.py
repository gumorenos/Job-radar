from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.db.enums import Classification, Confidence, FeedbackReason, JobStatus, WorkMode
from app.db.models import CandidateProfile, ClassificationFeedback, Job, MatchAnalysis
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


def _job_with_analysis() -> Job:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        profile = CandidateProfile(name="QA profile")
        session.add(profile)
        session.flush()
        job = Job(
            canonical_title="Strategic HR Business Partner",
            title_key="strategic hr business partner",
            company_name_raw="Example Corp",
            company_is_confidential=False,
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(job)
        session.flush()
        session.add(
            MatchAnalysis(
                job_id=job.id,
                candidate_profile_id=profile.id,
                overall_score=90,
                classification=Classification.HIGH_PRIORITY,
                confidence=Confidence.HIGH,
                strengths=["HRBP"],
                gaps=[],
                analyzer_version="qa-v1",
            )
        )
        session.commit()
        return job


def test_feedback_endpoint_preserves_system_classification_and_overrides_radar() -> None:
    job = _job_with_analysis()

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/radar/jobs/{job.id}/feedback",
            json={
                "human_classification": "REVIEW",
                "reason_code": "TITLE",
                "comment": "  El título necesita una revisión manual.  ",
            },
        )
        detail = client.get(f"/api/v1/radar/jobs/{job.id}")

    assert response.status_code == 201
    payload = response.json()
    assert payload["system_classification"] == "HIGH_PRIORITY"
    assert payload["human_classification"] == "REVIEW"
    assert payload["reason_code"] == "TITLE"
    assert payload["comment"] == "El título necesita una revisión manual."

    detail_payload = detail.json()
    assert detail_payload["effective_classification"] == "REVIEW"
    assert detail_payload["classification_source"] == "human"
    assert detail_payload["latest_analysis"]["classification"] == "HIGH_PRIORITY"
    assert detail_payload["latest_feedback"]["system_classification"] == "HIGH_PRIORITY"
    assert detail_payload["latest_feedback"]["human_classification"] == "REVIEW"
    assert detail_payload["latest_feedback"]["reason_code"] == "TITLE"
    assert detail_payload["latest_feedback"]["comment"] == (
        "El título necesita una revisión manual."
    )

    with get_session_factory()() as session:
        feedback = session.scalar(select(ClassificationFeedback))
        assert feedback is not None
        assert feedback.system_classification == Classification.HIGH_PRIORITY
        assert feedback.human_classification == Classification.REVIEW
        assert feedback.reason_code == FeedbackReason.TITLE


def test_new_feedback_becomes_effective_without_destroying_feedback_history() -> None:
    job = _job_with_analysis()

    with TestClient(app) as client:
        first = client.post(
            f"/api/v1/radar/jobs/{job.id}/feedback",
            json={"human_classification": "REVIEW", "reason_code": "TITLE"},
        )
        second = client.post(
            f"/api/v1/radar/jobs/{job.id}/feedback",
            json={
                "human_classification": "DISCARD",
                "reason_code": "SALARY",
                "comment": "No compensa para esta oportunidad.",
            },
        )
        detail = client.get(f"/api/v1/radar/jobs/{job.id}")

    assert first.status_code == 201
    assert second.status_code == 201
    detail_payload = detail.json()
    assert detail_payload["effective_classification"] == "DISCARD"
    assert detail_payload["latest_analysis"]["classification"] == "HIGH_PRIORITY"
    assert detail_payload["latest_feedback"]["human_classification"] == "DISCARD"
    assert detail_payload["latest_feedback"]["reason_code"] == "SALARY"

    with get_session_factory()() as session:
        count = session.scalar(select(func.count()).select_from(ClassificationFeedback))
        assert count == 2
        analyses = list(session.scalars(select(MatchAnalysis)))
        assert len(analyses) == 1
        assert analyses[0].classification == Classification.HIGH_PRIORITY


def test_feedback_requires_a_system_classification() -> None:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        job = Job(
            canonical_title="People Analytics Lead",
            title_key="people analytics lead",
            company_name_raw="Example Corp",
            company_is_confidential=False,
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(job)
        session.commit()

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/radar/jobs/{job.id}/feedback",
            json={"human_classification": "REVIEW", "reason_code": "OTHER"},
        )

    assert response.status_code == 409
