from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ops.openclaw_job_radar_sync import (
    build_ingestion_payload,
    candidate_files,
    event_idempotency_key,
    extract_vacancies,
    normalize_posting_source,
    parse_env_file,
)


def test_extract_vacancies_accepts_list_and_known_container_keys() -> None:
    row = {"title": "Senior HRBP"}
    assert extract_vacancies([row]) == [row]
    assert extract_vacancies({"vacancies": [row]}) == [row]
    assert extract_vacancies({"items": [row]}) == [row]


def test_bridge_mapping_is_conservative_and_preserves_raw(tmp_path: Path) -> None:
    source_file = tmp_path / "processed-vacancies-20260823.json"
    source_file.write_text("[]", encoding="utf-8")
    timestamp = datetime(2026, 8, 23, 20, 0, tzinfo=UTC).timestamp()
    os.utime(source_file, (timestamp, timestamp))

    record = {
        "source": "LinkedIn email",
        "title": "Senior People Analytics Analyst",
        "company": "Example Corp",
        "location": "Lima, Peru",
        "published": "hace 40 minutos",
        "url": "https://tracker.invalid/a",
        "url_final": "https://example.com/jobs/123",
        "note": "People Analytics and HR Analytics",
        "salary_condition": "Sueldo publicado",
        "salary_detail": "S/ 9,000",
        "salary_max_pen": 9000,
        "score": 9,
        "verdict": "revisar",
    }

    payload = build_ingestion_payload(record, source_file, 3)

    assert payload["ingestion_source"] == "openclaw"
    assert payload["posting_source"] == "linkedin"
    assert "external_id" not in payload
    assert payload["captured_at"] == "2026-08-23T20:00:00Z"
    assert payload["job"] == {
        "title": "Senior People Analytics Analyst",
        "company": "Example Corp",
        "location": "Lima, Peru",
        "description": "People Analytics and HR Analytics",
        "salary_text": "S/ 9,000 | Sueldo publicado",
        "url": "https://example.com/jobs/123",
    }
    # Relative publication text is metadata only; the bridge must not invent a timestamp.
    assert "published_at" not in payload["job"]
    assert "work_mode" not in payload["job"]
    assert "seniority" not in payload["job"]
    assert payload["metadata"]["published"] == "hace 40 minutos"
    assert payload["metadata"]["salary_max_pen"] == 9000
    assert payload["raw"] == record


def test_idempotency_key_is_stable_for_retry_and_changes_for_new_observation(
    tmp_path: Path,
) -> None:
    first_file = tmp_path / "processed-vacancies-a.json"
    second_file = tmp_path / "processed-vacancies-b.json"
    record = {"title": "HRBP", "company": "ACME"}

    first = event_idempotency_key(first_file, 0, record)
    retry = event_idempotency_key(first_file, 0, dict(record))
    new_file = event_idempotency_key(second_file, 0, record)
    changed_payload = event_idempotency_key(first_file, 0, {**record, "location": "Lima"})

    assert first == retry
    assert first != new_file
    assert first != changed_payload


def test_candidate_files_respect_activation_cutoff(tmp_path: Path) -> None:
    old = tmp_path / "processed-vacancies-old.json"
    new = tmp_path / "processed-vacancies-new.json"
    old.write_text("[]", encoding="utf-8")
    new.write_text("[]", encoding="utf-8")

    old_time = datetime(2026, 8, 20, tzinfo=UTC).timestamp()
    new_time = datetime(2026, 8, 23, 20, tzinfo=UTC).timestamp()
    os.utime(old, (old_time, old_time))
    os.utime(new, (new_time, new_time))

    cutoff = datetime(2026, 8, 23, 19, tzinfo=UTC)
    assert candidate_files(tmp_path, None, cutoff) == [new]
    assert candidate_files(tmp_path, old, cutoff) == [old]


def test_parse_env_and_source_normalization(tmp_path: Path) -> None:
    env_file = tmp_path / "bridge.env"
    env_file.write_text(
        "# comment\nJOB_RADAR_API_KEY='secret'\nJOB_RADAR_API_URL=http://127.0.0.1:8010/x\n",
        encoding="utf-8",
    )
    assert parse_env_file(env_file)["JOB_RADAR_API_KEY"] == "secret"
    assert normalize_posting_source("Jobsora alert") == "jobsora"
    assert normalize_posting_source("AgentMail") == "agentmail"
    assert normalize_posting_source("Other Board") == "Other Board"


def test_extract_vacancies_rejects_unknown_shape() -> None:
    with pytest.raises(ValueError, match="Processed vacancy JSON"):
        extract_vacancies({"unexpected": json.dumps([])})
