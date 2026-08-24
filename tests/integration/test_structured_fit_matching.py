from __future__ import annotations

from collections.abc import Generator
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.enums import Classification
from app.db.models import Job, MatchAnalysis
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.worker.tasks import claim_next_task, execute_task


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().api_key.get_secret_value()}"}


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


def _drain_worker() -> None:
    for _ in range(20):
        with get_session_factory()() as session:
            claimed = claim_next_task(session, "structured-fit-test")
        if claimed is None:
            return
        with get_session_factory()() as session:
            execute_task(session, claimed)
    raise AssertionError("Worker queue did not become idle.")


def _set_profile(client: TestClient, *, experience_years: float = 5) -> None:
    current = client.get("/api/v1/profile").json()
    current.pop("id")
    current.pop("remote_salary_min_pen")
    current.pop("rules")
    current.update(
        {
            "experience_years": experience_years,
            "degrees": ["Administración"],
            "skills": ["People Analytics"],
            "transferable_skills": ["Power BI"],
        }
    )
    response = client.put("/api/v1/profile", json=current)
    assert response.status_code == 200


def _ingest(client: TestClient, key: str, job: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/ingestions/jobs",
        headers={**_auth_headers(), "Idempotency-Key": key},
        json={
            "ingestion_source": "openclaw",
            "posting_source": "linkedin",
            "external_id": "structured-fit-job",
            "job": job,
        },
    )
    assert response.status_code == 202
    _drain_worker()


def _strong_job(**overrides: object) -> dict[str, object]:
    job: dict[str, object] = {
        "title": "Senior People Analytics Analyst",
        "company": "Structured Fit Corp",
        "location": "Lima",
        "work_mode": "hybrid",
        "salary_text": "S/ 9,000",
        "description": "People Analytics y HR Analytics para decisiones de Gestión Humana.",
        "url": "https://example.com/jobs/structured-fit",
    }
    job.update(overrides)
    return job


def test_five_vs_seven_years_forces_review_without_discarding_strong_fit() -> None:
    with TestClient(app) as client:
        _set_profile(client, experience_years=5)
        _ingest(
            client,
            "structured-gap",
            _strong_job(
                required_experience_years=7,
                required_degrees=["Administración"],
                required_skills=["People Analytics", "Power BI"],
            ),
        )

    with get_session_factory()() as session:
        job = session.scalar(select(Job))
        analysis = session.scalar(select(MatchAnalysis))
        assert job is not None
        assert analysis is not None
        assert job.required_experience_years is not None
        assert float(job.required_experience_years) == 7
        assert job.required_degrees == ["Administración"]
        assert job.required_skills == ["People Analytics", "Power BI"]
        assert analysis.classification == Classification.REVIEW
        assert analysis.recommendation == "REVISAR"
        assert analysis.analyzer_version == "rules-v5"
        assert analysis.rule_results["structured_fit_requires_review"] is True
        structured = cast(dict[str, object], analysis.skill_analysis["structured_fit"])
        experience = cast(dict[str, object], structured["experience"])
        degree = cast(dict[str, object], structured["degree"])
        skills = cast(dict[str, object], structured["skills"])
        assert experience["status"] == "PARTIALLY"
        assert degree["status"] == "MEETS"
        assert skills["status"] == "TRANSFERABLE"
        assert "brecha" in analysis.explanation.lower()


def test_all_structured_requirements_met_preserves_high_priority() -> None:
    with TestClient(app) as client:
        _set_profile(client, experience_years=7)
        _ingest(
            client,
            "structured-meets",
            _strong_job(
                required_experience_years=5,
                required_degrees=["Administración"],
                required_skills=["People Analytics"],
            ),
        )

    with get_session_factory()() as session:
        analysis = session.scalar(select(MatchAnalysis))
        assert analysis is not None
        assert analysis.classification == Classification.HIGH_PRIORITY
        structured = cast(dict[str, object], analysis.skill_analysis["structured_fit"])
        assert cast(dict[str, object], structured["experience"])["status"] == "MEETS"
        assert cast(dict[str, object], structured["degree"])["status"] == "MEETS"
        assert cast(dict[str, object], structured["skills"])["status"] == "MEETS"


def test_rediscovery_with_new_requirement_is_material_and_reanalyzes_latest_state() -> None:
    with TestClient(app) as client:
        _set_profile(client, experience_years=5)
        _ingest(client, "structured-rediscovery-1", _strong_job())

        with get_session_factory()() as session:
            first = list(session.scalars(select(MatchAnalysis).order_by(MatchAnalysis.created_at)))
            assert len(first) == 1
            assert first[0].classification == Classification.HIGH_PRIORITY

        _ingest(
            client,
            "structured-rediscovery-2",
            _strong_job(required_experience_years=7),
        )

    with get_session_factory()() as session:
        analyses = list(session.scalars(select(MatchAnalysis).order_by(MatchAnalysis.created_at)))
        assert len(analyses) == 2
        assert analyses[-1].classification == Classification.REVIEW
        structured = cast(dict[str, object], analyses[-1].skill_analysis["structured_fit"])
        assert cast(dict[str, object], structured["experience"])["status"] == "PARTIALLY"
