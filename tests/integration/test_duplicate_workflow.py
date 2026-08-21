from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.enums import DuplicateCandidateStatus, JobStatus
from app.db.models import DuplicateCandidate, Job, JobPosting, MatchAnalysis
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.worker.tasks import claim_next_task, execute_task


def _auth_headers() -> dict[str, str]:
    key = get_settings().api_key.get_secret_value()
    return {"Authorization": f"Bearer {key}"}


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
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


def _process_until_idle() -> None:
    for _ in range(20):
        with get_session_factory()() as session:
            claimed = claim_next_task(session, "duplicate-workflow-test")
        if claimed is None:
            return
        with get_session_factory()() as session:
            execute_task(session, claimed)
    raise AssertionError("Worker queue did not become idle.")


def _ingest(
    client: TestClient,
    key: str,
    *,
    title: str,
    url: str,
    company: str = "Duplicate QA Corp",
) -> None:
    response = client.post(
        "/api/v1/ingestions/jobs",
        headers={**_auth_headers(), "Idempotency-Key": key},
        json={
            "ingestion_source": "openclaw",
            "posting_source": "linkedin",
            "external_id": key,
            "job": {
                "title": title,
                "company": company,
                "location": "Lima",
                "work_mode": "hybrid",
                "description": "People Analytics y HR Analytics.",
                "url": url,
            },
        },
    )
    assert response.status_code == 202
    _process_until_idle()


def test_uncertain_duplicate_is_flagged_and_can_be_kept_separate() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "dup-keep-1",
            title="Senior People Analytics Analyst",
            url="https://example.com/jobs/dup-keep-1",
        )
        _ingest(
            client,
            "dup-keep-2",
            title="People Analytics Senior Analyst",
            url="https://example.com/jobs/dup-keep-2",
        )

        summary = client.get("/api/v1/radar/summary")
        candidates = client.get("/api/v1/radar/duplicates")

        assert summary.status_code == 200
        assert summary.json()["duplicates"] == 1
        assert candidates.status_code == 200
        payload = candidates.json()
        assert payload["total"] == 1
        candidate = payload["items"][0]
        assert candidate["status"] == "PENDING"
        assert float(candidate["confidence"]) >= 0.78
        assert {candidate["job_a"]["title"], candidate["job_b"]["title"]} == {
            "Senior People Analytics Analyst",
            "People Analytics Senior Analyst",
        }

        resolved = client.post(
            f"/api/v1/radar/duplicates/{candidate['id']}/resolve",
            json={"decision": "KEEP_SEPARATE"},
        )
        refreshed_summary = client.get("/api/v1/radar/summary")

    assert resolved.status_code == 200
    assert resolved.json()["status"] == "KEPT_SEPARATE"
    assert resolved.json()["resolved_survivor_job_id"] is None
    assert refreshed_summary.json()["duplicates"] == 0

    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 2
        assert all(job.status == JobStatus.ACTIVE for job in session.scalars(select(Job)))


def test_merge_preserves_sources_and_immutable_analysis_history() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "dup-merge-1",
            title="Senior People Analytics Analyst",
            url="https://example.com/jobs/dup-merge-1",
        )
        _ingest(
            client,
            "dup-merge-2",
            title="People Analytics Senior Analyst",
            url="https://example.com/jobs/dup-merge-2",
        )

        candidate = client.get("/api/v1/radar/duplicates").json()["items"][0]
        survivor_id = candidate["job_a"]["id"]
        duplicate_id = candidate["job_b"]["id"]

        resolved = client.post(
            f"/api/v1/radar/duplicates/{candidate['id']}/resolve",
            json={"decision": "MERGE", "survivor_job_id": survivor_id},
        )
        summary = client.get("/api/v1/radar/summary")

    assert resolved.status_code == 200
    assert resolved.json()["status"] == "MERGED"
    assert resolved.json()["resolved_survivor_job_id"] == survivor_id
    assert summary.json()["duplicates"] == 0

    with get_session_factory()() as session:
        survivor = session.get(Job, survivor_id)
        duplicate = session.get(Job, duplicate_id)
        assert survivor is not None
        assert duplicate is not None
        assert survivor.status == JobStatus.ACTIVE
        assert duplicate.status == JobStatus.CLOSED
        assert duplicate.parent_job_id == survivor.id

        postings = list(session.scalars(select(JobPosting)))
        assert len(postings) == 2
        assert {posting.job_id for posting in postings} == {survivor.id}

        # MatchAnalysis is an audit record. Human duplicate resolution must not rewrite
        # the job each historical analysis originally evaluated.
        analyses = list(session.scalars(select(MatchAnalysis)))
        assert len(analyses) == 2
        assert {analysis.job_id for analysis in analyses} == {survivor.id, duplicate.id}

        duplicate_candidate = session.scalar(select(DuplicateCandidate))
        assert duplicate_candidate is not None
        assert duplicate_candidate.status == DuplicateCandidateStatus.MERGED


def test_unrelated_jobs_are_not_flagged_as_possible_duplicates() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "dup-none-1",
            title="People Analytics Lead",
            url="https://example.com/jobs/dup-none-1",
        )
        _ingest(
            client,
            "dup-none-2",
            title="Finance Manager",
            url="https://example.com/jobs/dup-none-2",
        )
        candidates = client.get("/api/v1/radar/duplicates")

    assert candidates.status_code == 200
    assert candidates.json()["total"] == 0
