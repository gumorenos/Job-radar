from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import get_engine
from app.main import app


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    career_evidence,
                    cv_versions,
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


def _create_evidence(client: TestClient, *, generated_by_ai: bool = False) -> dict[str, object]:
    response = client.post(
        "/api/v1/evidence",
        json={
            "statement": "Gestioné onboarding de alto volumen en operaciones regionales.",
            "category": "ONBOARDING",
            "tags": ["onboarding", "scale"],
            "source_type": "USER_INTERVIEW",
            "generated_by_ai": generated_by_ai,
            "source_reference": "enrich-session-1",
            "source_metadata": {"audio_start_seconds": 42, "audio_end_seconds": 88},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_ai_extracted_evidence_starts_unverified_and_can_be_verified() -> None:
    with TestClient(app) as client:
        created = _create_evidence(client, generated_by_ai=True)
        assert created["verification_status"] == "UNVERIFIED"
        assert created["verified_at"] is None

        verified = client.post(
            f"/api/v1/evidence/{created['id']}/verification",
            json={"status": "VERIFIED", "notes": "Confirmado por el usuario."},
        )

    assert verified.status_code == 200
    body = verified.json()
    assert body["verification_status"] == "VERIFIED"
    assert body["reviewed_at"] is not None
    assert body["verified_at"] is not None
    assert body["notes"] == "Confirmado por el usuario."


def test_verified_evidence_claim_is_immutable_but_notes_remain_editable() -> None:
    with TestClient(app) as client:
        created = _create_evidence(client)
        verified = client.post(
            f"/api/v1/evidence/{created['id']}/verification",
            json={"status": "VERIFIED"},
        )
        assert verified.status_code == 200

        rejected_edit = client.patch(
            f"/api/v1/evidence/{created['id']}",
            json={"statement": "Una versión distinta del hecho."},
        )
        notes_edit = client.patch(
            f"/api/v1/evidence/{created['id']}",
            json={"notes": "Contexto adicional sin cambiar el hecho."},
        )

    assert rejected_edit.status_code == 409
    assert "inmutable" in rejected_edit.json()["detail"]
    assert notes_edit.status_code == 200
    assert notes_edit.json()["verification_status"] == "VERIFIED"
    assert notes_edit.json()["notes"] == "Contexto adicional sin cambiar el hecho."


def test_editing_partial_claim_resets_it_to_unverified() -> None:
    with TestClient(app) as client:
        created = _create_evidence(client)
        reviewed = client.post(
            f"/api/v1/evidence/{created['id']}/verification",
            json={"status": "PARTIAL"},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["reviewed_at"] is not None

        edited = client.patch(
            f"/api/v1/evidence/{created['id']}",
            json={"statement": "Gestioné onboarding regional de alto volumen."},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["verification_status"] == "UNVERIFIED"
    assert body["reviewed_at"] is None
    assert body["verified_at"] is None


def test_archive_hides_evidence_from_default_listing_but_keeps_history() -> None:
    with TestClient(app) as client:
        created = _create_evidence(client)
        archived = client.post(f"/api/v1/evidence/{created['id']}/archive")
        default_listing = client.get("/api/v1/evidence")
        history_listing = client.get("/api/v1/evidence?include_archived=true")

    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert default_listing.status_code == 200
    assert default_listing.json()["total"] == 0
    assert history_listing.status_code == 200
    assert history_listing.json()["total"] == 1
    assert history_listing.json()["items"][0]["id"] == created["id"]


def test_listing_filters_by_status_source_and_tag() -> None:
    with TestClient(app) as client:
        first = _create_evidence(client)
        second = client.post(
            "/api/v1/evidence",
            json={
                "statement": "Construí dashboards de People Analytics.",
                "category": "PEOPLE_ANALYTICS",
                "tags": ["analytics", "dashboards"],
                "source_type": "CV",
            },
        )
        assert second.status_code == 201
        verified = client.post(
            f"/api/v1/evidence/{first['id']}/verification",
            json={"status": "VERIFIED"},
        )
        assert verified.status_code == 200

        filtered = client.get(
            "/api/v1/evidence"
            "?verification_status=VERIFIED"
            "&source_type=USER_INTERVIEW"
            "&tag=onboarding"
        )

    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == first["id"]
