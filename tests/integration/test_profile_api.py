from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.db.models import CandidateProfile
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


def _update_payload(current: dict[str, object]) -> dict[str, object]:
    return {
        "name": current["name"],
        "salary_min_pen": current["salary_min_pen"],
        "remote_salary_multiplier": current["remote_salary_multiplier"],
        "target_locations": current["target_locations"],
        "target_roles": current["target_roles"],
        "target_areas": current["target_areas"],
        "adjacent_areas": current["adjacent_areas"],
        "daily_review_time": current["daily_review_time"],
        "timezone": current["timezone"],
    }


def test_get_profile_creates_single_default_profile() -> None:
    with TestClient(app) as client:
        first = client.get("/api/v1/profile")
        second = client.get("/api/v1/profile")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["salary_min_pen"] == "7000.00"
    assert first.json()["remote_salary_min_pen"] == "7700.0000"
    assert first.json()["timezone"] == "America/Lima"

    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(CandidateProfile)) == 1


def test_update_profile_normalizes_lists_and_preserves_rule_metadata() -> None:
    with TestClient(app) as client:
        current = client.get("/api/v1/profile").json()
        updated = client.put(
            "/api/v1/profile",
            json={
                "name": " Búsqueda principal ",
                "salary_min_pen": 7200,
                "remote_salary_multiplier": 1.15,
                "target_locations": ["Lima Metropolitana", "Remote LATAM", "remote latam", ""],
                "target_roles": ["Strategic HRBP", "Manager", " Strategic HRBP "],
                "target_areas": ["People Analytics", "Compensaciones"],
                "adjacent_areas": ["People Operations", "HRIS"],
                "daily_review_time": "20:30",
                "timezone": " America/Lima ",
            },
        )
        refreshed = client.get("/api/v1/profile")

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["name"] == "Búsqueda principal"
    assert payload["salary_min_pen"] == "7200.00"
    assert payload["remote_salary_multiplier"] == "1.15"
    assert payload["remote_salary_min_pen"] == "8280.0000"
    assert payload["target_locations"] == ["Lima Metropolitana", "Remote LATAM"]
    assert payload["target_roles"] == ["Strategic HRBP", "Manager"]
    assert payload["daily_review_time"] == "20:30:00"
    assert payload["timezone"] == "America/Lima"
    assert payload["rules"] == current["rules"]
    assert refreshed.json() == payload

    with get_session_factory()() as session:
        profile = session.scalar(select(CandidateProfile))
        assert profile is not None
        assert profile.salary_min_pen == Decimal("7200")
        assert profile.remote_salary_multiplier == Decimal("1.15")
        assert profile.rules == {"source": "phase-0-confirmed-rules"}


def test_update_profile_rejects_invalid_multiplier() -> None:
    with TestClient(app) as client:
        current = client.get("/api/v1/profile").json()
        payload = _update_payload(current)
        payload["remote_salary_multiplier"] = 0.5
        response = client.put("/api/v1/profile", json=payload)

    assert response.status_code == 422


def test_update_profile_rejects_invalid_timezone() -> None:
    with TestClient(app) as client:
        current = client.get("/api/v1/profile").json()
        payload = _update_payload(current)
        payload["timezone"] = "Mars/Olympus"
        response = client.put("/api/v1/profile", json=payload)

    assert response.status_code == 422
