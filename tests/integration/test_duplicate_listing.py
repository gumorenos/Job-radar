from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.db.enums import DuplicateCandidateStatus, JobStatus, PostingStatus, WorkMode
from app.db.models import Company, DuplicateCandidate, Job, JobPosting
from app.db.session import get_engine, get_session_factory
from app.main import app


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


def _job(index: int, side: str, *, title: str | None = None) -> Job:
    now = datetime.now(UTC)
    return Job(
        canonical_title=title or f"People Partner {index} {side}",
        title_key=(title or f"People Partner {index} {side}").casefold(),
        company_name_raw=f"Duplicate Listing Corp {index}",
        company_is_confidential=False,
        location_text="Lima",
        work_mode=WorkMode.HYBRID,
        status=JobStatus.ACTIVE,
        first_seen_at=now,
        last_seen_at=now,
    )


def _create_candidate(index: int, *, title: str | None = None) -> DuplicateCandidate:
    with get_session_factory()() as session:
        job_a = _job(index, "A", title=title)
        job_b = _job(index, "B")
        session.add_all([job_a, job_b])
        session.flush()
        candidate = DuplicateCandidate(
            job_a_id=job_a.id,
            job_b_id=job_b.id,
            confidence=Decimal("0.8500") + Decimal(index) / Decimal("10000"),
            reasons={"title_similarity": 0.85},
            status=DuplicateCandidateStatus.PENDING,
        )
        session.add(candidate)
        session.commit()
        return candidate


def test_duplicate_listing_supports_offset_with_exact_total() -> None:
    [_create_candidate(index) for index in range(3)]

    with TestClient(app) as client:
        first = client.get("/api/v1/radar/duplicates?limit=1&offset=0")
        second = client.get("/api/v1/radar/duplicates?limit=1&offset=1")
        beyond = client.get("/api/v1/radar/duplicates?limit=1&offset=3")
        invalid = client.get("/api/v1/radar/duplicates?offset=-1")

    assert first.status_code == 200
    assert second.status_code == 200
    assert beyond.status_code == 200
    assert invalid.status_code == 422
    assert first.json()["total"] == 3
    assert second.json()["total"] == 3
    assert beyond.json()["total"] == 3
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
    assert beyond.json()["items"] == []


def test_duplicate_search_covers_job_normalized_company_and_posting_fields() -> None:
    title_candidate = _create_candidate(1, title="Senior Workforce Analytics Lead")
    _create_candidate(2, title="Strategic HR Business Partner")

    now = datetime.now(UTC)
    with get_session_factory()() as session:
        title_row = session.get(DuplicateCandidate, title_candidate.id)
        assert title_row is not None
        job_a = session.get(Job, title_row.job_a_id)
        assert job_a is not None

        company = Company(
            name="Normalized People Holdings",
            normalized_name="normalized people holdings",
        )
        session.add(company)
        session.flush()
        job_a.company_id = company.id
        job_a.company_name_raw = "Legacy Alias"
        session.add(
            JobPosting(
                job_id=job_a.id,
                posting_source="linkedin",
                source_url_raw="https://example.com/jobs/source-search",
                source_url_normalized="https://example.com/jobs/source-search",
                canonical_url="https://example.com/jobs/source-search",
                title_raw="Workforce Intelligence Principal",
                company_raw="Source Alias Talent",
                location_raw="Miraflores",
                description_raw="Analytics role",
                salary_text="S/ 9,000",
                first_seen_at=now,
                last_seen_at=now,
                posting_status=PostingStatus.ACTIVE,
            )
        )
        session.commit()

    with TestClient(app) as client:
        by_title = client.get("/api/v1/radar/duplicates?q=workforce%20analytics")
        by_company = client.get("/api/v1/radar/duplicates?q=normalized%20people")
        by_source = client.get("/api/v1/radar/duplicates?q=source%20alias")
        by_location = client.get("/api/v1/radar/duplicates?q=miraflores")
        missing = client.get("/api/v1/radar/duplicates?q=finance")

    expected_id = str(title_candidate.id)
    assert by_title.status_code == 200
    assert by_title.json()["total"] == 1
    assert by_title.json()["items"][0]["id"] == expected_id
    assert by_company.json()["items"][0]["id"] == expected_id
    assert by_source.json()["items"][0]["id"] == expected_id
    assert by_location.json()["items"][0]["id"] == expected_id
    assert missing.json() == {"items": [], "total": 0}


def test_duplicate_listing_query_count_is_bounded() -> None:
    [_create_candidate(index) for index in range(8)]
    statements = 0

    def count_statement(*_: object, **__: object) -> None:
        nonlocal statements
        statements += 1

    engine = get_engine()
    with TestClient(app) as client:
        event.listen(engine, "before_cursor_execute", count_statement)
        try:
            response = client.get("/api/v1/radar/duplicates?limit=8")
        finally:
            event.remove(engine, "before_cursor_execute", count_statement)

    assert response.status_code == 200
    assert response.json()["total"] == 8
    assert len(response.json()["items"]) == 8
    assert statements <= 6
