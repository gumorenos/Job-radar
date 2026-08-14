from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class IncomingJob(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    work_mode: str | None = Field(default=None, max_length=80)
    employment_type: str | None = Field(default=None, max_length=120)
    salary_text: str | None = Field(default=None, max_length=500)
    description: str | None = None
    url: str | None = None
    published_at: datetime | None = None


class JobIngestionRequest(BaseModel):
    ingestion_source: str = Field(min_length=1, max_length=80)
    posting_source: str | None = Field(default=None, max_length=80)
    external_id: str | None = Field(default=None, max_length=300)
    captured_at: datetime | None = None
    job: IncomingJob
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_minimum_identity(self) -> JobIngestionRequest:
        if not any((self.external_id, self.job.url, self.job.title)):
            raise ValueError("At least one of external_id, job.url, or job.title is required.")
        return self


class JobIngestionResponse(BaseModel):
    ingestion_id: UUID
    status: str
    received_at: datetime
