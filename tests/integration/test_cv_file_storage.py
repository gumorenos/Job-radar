from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine
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


def _clear_cv_storage() -> None:
    shutil.rmtree(get_settings().storage_path / "cvs", ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_state() -> Generator[None]:
    _truncate_database()
    _clear_cv_storage()
    yield
    _truncate_database()
    _clear_cv_storage()


def _create_cv(client: TestClient, name: str = "CV Base") -> dict[str, object]:
    response = client.post("/api/v1/cvs", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_pdf_upload_is_stored_with_generated_path_and_can_be_downloaded() -> None:
    body = b"%PDF-1.7\nJob Radar CV test"
    with TestClient(app) as client:
        cv = _create_cv(client)
        cv_id = cv["id"]
        upload = client.put(
            f"/api/v1/cvs/{cv_id}/file",
            params={"filename": "../../CV Original.pdf"},
            headers={"Content-Type": "application/pdf"},
            content=body,
        )
        download = client.get(f"/api/v1/cvs/{cv_id}/file")

    assert upload.status_code == 200
    payload = upload.json()
    assert payload["has_file"] is True
    assert payload["original_filename"] == "CV Original.pdf"
    storage_path = str(payload["storage_path"])
    assert storage_path.startswith("cvs/")
    assert ".." not in storage_path

    physical_path = (get_settings().storage_path / storage_path).resolve()
    assert physical_path.is_relative_to(get_settings().storage_path.resolve())
    assert physical_path.read_bytes() == body
    assert physical_path.stat().st_mode & 0o777 == 0o600

    assert download.status_code == 200
    assert download.content == body
    assert download.headers["content-type"].startswith("application/pdf")
    assert "attachment" in download.headers["content-disposition"]


def test_file_is_immutable_within_one_cv_version() -> None:
    first_body = b"%PDF-1.7\nfirst"
    second_body = b"%PDF-1.7\nsecond"
    with TestClient(app) as client:
        cv = _create_cv(client)
        cv_id = cv["id"]
        first = client.put(
            f"/api/v1/cvs/{cv_id}/file",
            params={"filename": "cv.pdf"},
            headers={"Content-Type": "application/pdf"},
            content=first_body,
        )
        second = client.put(
            f"/api/v1/cvs/{cv_id}/file",
            params={"filename": "replacement.pdf"},
            headers={"Content-Type": "application/pdf"},
            content=second_body,
        )
        download = client.get(f"/api/v1/cvs/{cv_id}/file")

    assert first.status_code == 200
    assert second.status_code == 409
    assert "nueva versión" in second.json()["detail"]
    assert download.content == first_body


def test_invalid_file_content_is_rejected_without_attaching_it() -> None:
    with TestClient(app) as client:
        cv = _create_cv(client)
        cv_id = cv["id"]
        rejected = client.put(
            f"/api/v1/cvs/{cv_id}/file",
            params={"filename": "fake.pdf"},
            headers={"Content-Type": "application/pdf"},
            content=b"not actually a pdf",
        )
        refreshed = client.get(f"/api/v1/cvs/{cv_id}")
        missing = client.get(f"/api/v1/cvs/{cv_id}/file")

    assert rejected.status_code == 422
    assert refreshed.json()["has_file"] is False
    assert refreshed.json()["storage_path"] is None
    assert missing.status_code == 404


def test_client_cannot_set_arbitrary_storage_path_on_cv_create() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/cvs",
            json={
                "name": "CV with untrusted path",
                "storage_path": "../../etc/passwd",
                "original_filename": "metadata-only.pdf",
            },
        )

    assert response.status_code == 201
    assert response.json()["storage_path"] is None
    assert response.json()["has_file"] is False


def test_upload_requires_matching_supported_extension_and_media_type() -> None:
    with TestClient(app) as client:
        cv = _create_cv(client)
        cv_id = cv["id"]
        mismatch = client.put(
            f"/api/v1/cvs/{cv_id}/file",
            params={"filename": "cv.docx"},
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF-1.7\nvalid bytes but wrong name",
        )
        unsupported = client.put(
            f"/api/v1/cvs/{cv_id}/file",
            params={"filename": "cv.exe"},
            headers={"Content-Type": "application/octet-stream"},
            content=b"binary",
        )

    assert mismatch.status_code == 422
    assert unsupported.status_code == 422


def test_stored_file_path_stays_under_configured_root() -> None:
    with TestClient(app) as client:
        cv = _create_cv(client, "CV TXT")
        cv_id = cv["id"]
        response = client.put(
            f"/api/v1/cvs/{cv_id}/file",
            params={"filename": "folder\\..\\notes.txt"},
            headers={"Content-Type": "text/plain; charset=utf-8"},
            content=b"Experiencia de People Analytics",
        )

    assert response.status_code == 200
    relative = Path(response.json()["storage_path"])
    physical = (get_settings().storage_path / relative).resolve()
    assert physical.is_relative_to(get_settings().storage_path.resolve())
    assert response.json()["original_filename"] == "notes.txt"
