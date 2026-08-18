from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.db.enums import CvApprovalStatus
from app.db.models import CandidateProfile, CvVersion
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


def test_manual_cv_is_approved_and_can_be_active_base() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/cvs",
            json={
                "name": "CV Base",
                "is_base": True,
                "activate": True,
                "content_text": "Experiencia real del candidato.",
                "original_filename": "cv-base.pdf",
            },
        )
        listing = client.get("/api/v1/cvs")

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "CV Base"
    assert payload["slug"] == "cv-base"
    assert payload["version"] == 1
    assert payload["is_base"] is True
    assert payload["is_active"] is True
    assert payload["approval_status"] == "APPROVED"
    assert payload["generated_by_ai"] is False
    assert payload["approved_at"] is not None

    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(CandidateProfile)) == 1
        cv = session.scalar(select(CvVersion))
        assert cv is not None
        assert cv.approval_status == CvApprovalStatus.APPROVED


def test_ai_cv_requires_explicit_approval_before_activation() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/cvs",
            json={
                "name": "CV HRBP",
                "generated_by_ai": True,
                "target_role": "Strategic HRBP",
                "content_text": "Borrador generado para revisión humana.",
            },
        )
        cv_id = created.json()["id"]
        blocked = client.post(f"/api/v1/cvs/{cv_id}/activate")
        approved = client.post(
            f"/api/v1/cvs/{cv_id}/approval",
            json={"status": "APPROVED"},
        )
        activated = client.post(f"/api/v1/cvs/{cv_id}/activate")

    assert created.status_code == 201
    assert created.json()["approval_status"] == "DRAFT"
    assert created.json()["approved_at"] is None
    assert blocked.status_code == 409
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "APPROVED"
    assert approved.json()["approved_at"] is not None
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True


def test_same_cv_name_creates_new_version_without_overwriting_original() -> None:
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/cvs",
            json={"name": "CV People Analytics", "content_text": "Versión original"},
        )
        second = client.post(
            "/api/v1/cvs",
            json={
                "name": "CV People Analytics",
                "parent_cv_id": first.json()["id"],
                "content_text": "Versión ajustada",
            },
        )
        listing = client.get("/api/v1/cvs")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2
    assert second.json()["parent_cv_id"] == first.json()["id"]
    assert listing.json()["total"] == 2

    with get_session_factory()() as session:
        versions = list(
            session.scalars(select(CvVersion).order_by(CvVersion.version.asc()))
        )
        assert [cv.content_text for cv in versions] == ["Versión original", "Versión ajustada"]


def test_activating_another_approved_cv_deactivates_previous_one() -> None:
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/cvs",
            json={"name": "CV Base", "is_base": True, "activate": True},
        )
        second = client.post(
            "/api/v1/cvs",
            json={"name": "CV Compensaciones", "activate": True},
        )
        refreshed_first = client.get(f"/api/v1/cvs/{first.json()['id']}")

    assert first.status_code == 201
    assert second.status_code == 201
    assert refreshed_first.json()["is_active"] is False
    assert second.json()["is_active"] is True
