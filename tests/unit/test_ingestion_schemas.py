from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domains.ingestion.schemas import IncomingJob, JobIngestionRequest


def test_minimal_ingestion_accepts_title_only() -> None:
    payload = JobIngestionRequest(
        ingestion_source="openclaw",
        posting_source="linkedin",
        job=IncomingJob(title="HR Business Partner"),
    )

    assert payload.job.title == "HR Business Partner"


def test_structured_salary_and_location_facts_are_supported() -> None:
    job = IncomingJob.model_validate(
        {
            "title": "People Analytics Lead",
            "country": "Peru",
            "city": "Lima",
            "seniority": "Lead",
            "salary_min": "8000",
            "salary_max": "9500",
            "currency": "PEN",
            "salary_period": "month",
        }
    )

    assert job.country == "Peru"
    assert job.city == "Lima"
    assert job.seniority == "Lead"
    assert job.salary_min == Decimal("8000")
    assert job.salary_max == Decimal("9500")
    assert job.currency == "PEN"


def test_ingestion_rejects_payload_without_identity() -> None:
    with pytest.raises(ValidationError):
        JobIngestionRequest(
            ingestion_source="openclaw",
            job=IncomingJob(),
        )
