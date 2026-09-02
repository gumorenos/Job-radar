from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.enums import JobStatus, WorkMode
from app.db.models import Job
from app.db.session import get_engine, get_session_factory
from app.main import app


def _truncate_database() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    job_application_events,
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


def _create_job() -> Job:
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        job = Job(
            canonical_title="Senior People Analytics Analyst",
            title_key="senior people analytics analyst",
            company_name_raw="Cockpit QA Corp",
            company_is_confidential=False,
            location_text="Lima",
            work_mode=WorkMode.HYBRID,
            status=JobStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(job)
        session.commit()
        return job


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_application_defaults_and_stage_transition_create_operational_plan() -> None:
    job = _create_job()
    before = datetime.now(UTC)

    with TestClient(app) as client:
        created = client.post(f"/api/v1/applications/jobs/{job.id}")
        application = created.json()["application"]
        application_id = application["id"]
        applied = client.patch(
            f"/api/v1/applications/{application_id}",
            json={"stage": "APPLIED"},
        )
        timeline = client.get(f"/api/v1/applications/{application_id}/timeline")

    assert created.status_code == 200
    assert application["next_action"] == "Preparar postulación"
    assert application["next_action_due_at"] is None
    assert application["follow_up_due_at"] is None

    assert applied.status_code == 200
    payload = applied.json()
    assert payload["stage"] == "APPLIED"
    assert payload["next_action"] == "Enviar seguimiento"
    assert payload["applied_at"] is not None
    assert payload["next_action_due_at"] == payload["follow_up_due_at"]
    due_at = _parse(payload["follow_up_due_at"])
    assert before + timedelta(days=6, hours=23) <= due_at
    assert due_at <= datetime.now(UTC) + timedelta(days=7, minutes=1)

    events = timeline.json()["items"]
    assert [item["event_type"] for item in events] == ["CREATED", "STAGE_CHANGED"]
    assert events[0]["to_stage"] == "TO_APPLY"
    assert events[1]["from_stage"] == "TO_APPLY"
    assert events[1]["to_stage"] == "APPLIED"


def test_repeating_same_stage_does_not_move_follow_up_or_append_stage_event() -> None:
    job = _create_job()

    with TestClient(app) as client:
        application_id = client.post(f"/api/v1/applications/jobs/{job.id}").json()[
            "application"
        ]["id"]
        first = client.patch(
            f"/api/v1/applications/{application_id}",
            json={"stage": "APPLIED"},
        ).json()
        second = client.patch(
            f"/api/v1/applications/{application_id}",
            json={"stage": "APPLIED"},
        ).json()
        timeline = client.get(f"/api/v1/applications/{application_id}/timeline").json()[
            "items"
        ]

    assert second["applied_at"] == first["applied_at"]
    assert second["next_action"] == first["next_action"]
    assert second["next_action_due_at"] == first["next_action_due_at"]
    assert second["follow_up_due_at"] == first["follow_up_due_at"]
    assert [item["event_type"] for item in timeline] == ["CREATED", "STAGE_CHANGED"]


def test_explicit_plan_overrides_stage_defaults_and_is_searchable() -> None:
    job = _create_job()
    due_at = datetime.now(UTC) + timedelta(days=3)

    with TestClient(app) as client:
        application_id = client.post(f"/api/v1/applications/jobs/{job.id}").json()[
            "application"
        ]["id"]
        response = client.patch(
            f"/api/v1/applications/{application_id}",
            json={
                "stage": "APPLIED",
                "next_action": "Contactar a recruiter regional",
                "next_action_due_at": due_at.isoformat(),
                "follow_up_due_at": due_at.isoformat(),
            },
        )
        listing = client.get("/api/v1/applications?stage=APPLIED&q=recruiter")

    assert response.status_code == 200
    payload = response.json()
    assert payload["next_action"] == "Contactar a recruiter regional"
    assert _parse(payload["next_action_due_at"]) == due_at
    assert _parse(payload["follow_up_due_at"]) == due_at
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == application_id


def test_follow_up_completion_reschedules_and_can_stop_future_followups() -> None:
    job = _create_job()

    with TestClient(app) as client:
        application_id = client.post(f"/api/v1/applications/jobs/{job.id}").json()[
            "application"
        ]["id"]
        client.patch(
            f"/api/v1/applications/{application_id}",
            json={"stage": "APPLIED"},
        )
        first = client.post(
            f"/api/v1/applications/{application_id}/follow-up-complete",
            json={"next_follow_up_days": 10},
        )
        second = client.post(
            f"/api/v1/applications/{application_id}/follow-up-complete",
            json={"next_follow_up_days": None},
        )
        timeline = client.get(f"/api/v1/applications/{application_id}/timeline")

    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["last_follow_up_at"] is not None
    assert first_payload["next_action"] == "Enviar segundo seguimiento"
    first_due = _parse(first_payload["follow_up_due_at"])
    assert datetime.now(UTC) + timedelta(days=9, hours=23) <= first_due
    assert first_due <= datetime.now(UTC) + timedelta(days=10, minutes=1)

    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["next_action"] == "Esperar respuesta"
    assert second_payload["next_action_due_at"] is None
    assert second_payload["follow_up_due_at"] is None
    assert second_payload["last_follow_up_at"] is not None

    event_types = [item["event_type"] for item in timeline.json()["items"]]
    assert event_types == [
        "CREATED",
        "STAGE_CHANGED",
        "FOLLOW_UP_COMPLETED",
        "FOLLOW_UP_COMPLETED",
    ]


def test_interview_and_closed_stages_clear_stale_follow_up_plan() -> None:
    job = _create_job()

    with TestClient(app) as client:
        application_id = client.post(f"/api/v1/applications/jobs/{job.id}").json()[
            "application"
        ]["id"]
        client.patch(
            f"/api/v1/applications/{application_id}",
            json={"stage": "APPLIED"},
        )
        interview = client.patch(
            f"/api/v1/applications/{application_id}",
            json={"stage": "INTERVIEW"},
        )
        closed = client.patch(
            f"/api/v1/applications/{application_id}",
            json={"stage": "CLOSED"},
        )
        invalid_follow_up = client.post(
            f"/api/v1/applications/{application_id}/follow-up-complete",
            json={},
        )

    assert interview.status_code == 200
    interview_payload = interview.json()
    assert interview_payload["next_action"] == "Preparar entrevista"
    assert interview_payload["next_action_due_at"] is None
    assert interview_payload["follow_up_due_at"] is None

    assert closed.status_code == 200
    closed_payload = closed.json()
    assert closed_payload["next_action"] is None
    assert closed_payload["next_action_due_at"] is None
    assert closed_payload["follow_up_due_at"] is None
    assert closed_payload["closed_at"] is not None

    assert invalid_follow_up.status_code == 409


def test_manual_plan_update_appends_history_without_rewriting_prior_events() -> None:
    job = _create_job()

    with TestClient(app) as client:
        application_id = client.post(f"/api/v1/applications/jobs/{job.id}").json()[
            "application"
        ]["id"]
        before = client.get(f"/api/v1/applications/{application_id}/timeline").json()[
            "items"
        ]
        update = client.patch(
            f"/api/v1/applications/{application_id}",
            json={"next_action": "Adaptar CV de People Analytics"},
        )
        after = client.get(f"/api/v1/applications/{application_id}/timeline").json()[
            "items"
        ]

    assert update.status_code == 200
    assert update.json()["next_action"] == "Adaptar CV de People Analytics"
    assert len(before) == 1
    assert len(after) == 2
    assert after[0] == before[0]
    assert after[1]["event_type"] == "PLAN_UPDATED"
    assert after[1]["note"] == "Adaptar CV de People Analytics"
