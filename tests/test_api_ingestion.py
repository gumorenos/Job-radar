from __future__ import annotations

import json


def test_ingestion_is_idempotent(monkeypatch, tmp_path):
    db_path = tmp_path / "job-radar-test.sqlite"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "profile_name": "test-profile",
                "must_review_terms": ["hr business partner", "people analytics"],
                "positive_terms": ["lead", "manager", "senior"],
                "negative_terms": ["intern", "practicante"],
                "remote_terms": ["remote", "remoto", "lima"],
                "salary_target_pen": 7000,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("JOB_RADAR_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("JOB_RADAR_PROFILE_PATH", str(profile_path))
    monkeypatch.setenv("JOB_RADAR_CANDIDATE_PROFILE_PATH", str(tmp_path / "missing-candidate.json"))
    monkeypatch.setenv("JOB_RADAR_ALLOW_UNAUTHENTICATED", "true")

    from fastapi.testclient import TestClient

    from job_radar_app.database import reset_database_state
    from job_radar_app.settings import get_settings

    get_settings.cache_clear()
    reset_database_state()

    from job_radar_app.api import app

    payload = {
        "source": "openclaw",
        "source_run_id": "daily-2026-07-26",
        "postings": [
            {
                "external_id": "linkedin-123",
                "title": "HR Business Partner - People Analytics Lead",
                "company": "Example Corp",
                "location": "Lima, Peru",
                "modality": "hybrid",
                "published_at": "2026-07-26",
                "salary_text": "S/ 8,000",
                "url": "https://example.com/jobs/123?utm_source=test",
                "description": "Strategic HRBP role supporting leaders with people analytics.",
            }
        ],
    }

    with TestClient(app) as client:
        first = client.post("/api/v1/postings/ingest", json=payload)
        assert first.status_code == 200, first.text
        assert first.json()["created"] == 1
        assert len(first.json()["new_relevant"]) == 1

        replay = client.post("/api/v1/postings/ingest", json=payload)
        assert replay.status_code == 200, replay.text
        assert replay.json()["idempotent_replay"] is True
        assert replay.json()["created"] == 1

        jobs = client.get("/api/v1/jobs")
        assert jobs.status_code == 200, jobs.text
        assert len(jobs.json()) == 1
        assert jobs.json()[0]["company"] == "Example Corp"
