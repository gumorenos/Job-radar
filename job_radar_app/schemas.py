from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PostingIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    external_id: str | None = None
    source: str | None = None
    title: str
    company: str | None = None
    location: str | None = None
    modality: str | None = None
    remote: str | bool | None = None
    published_at: str | None = None
    published: str | None = None
    accessed_at: str | None = None
    salary_text: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    url: str | None = None
    description: str | None = None


class IngestionBatchIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = Field(min_length=1, max_length=80)
    source_run_id: str = Field(min_length=1, max_length=200)
    postings: list[PostingIn] = Field(min_length=1, max_length=500)


class JobSummary(BaseModel):
    id: str
    source: str
    title: str
    company: str | None = None
    location: str | None = None
    remote: str | None = None
    published: str | None = None
    salary_text: str | None = None
    url: str | None = None
    score: int
    verdict: str
    status: str
    first_seen_at: str
    last_seen_at: str


class IngestionResult(BaseModel):
    ingestion_run_id: str
    source: str
    source_run_id: str
    received: int
    created: int
    updated: int
    duplicates: int
    new_relevant: list[JobSummary]
    idempotent_replay: bool = False


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str


class ErrorResponse(BaseModel):
    detail: str
    context: dict[str, Any] | None = None
