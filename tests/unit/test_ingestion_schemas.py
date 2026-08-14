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


def test_ingestion_rejects_payload_without_identity() -> None:
    with pytest.raises(ValidationError):
        JobIngestionRequest(
            ingestion_source="openclaw",
            job=IncomingJob(),
        )
