from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


def _clean_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Debe ser una lista de textos.")

    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            raise ValueError("Cada requisito debe ser texto.")
        item = raw.strip()
        if not item:
            continue
        if len(item) > 200:
            raise ValueError("Cada requisito debe tener como máximo 200 caracteres.")
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


class IncomingJob(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=120)
    work_mode: str | None = Field(default=None, max_length=80)
    employment_type: str | None = Field(default=None, max_length=120)
    seniority: str | None = Field(default=None, max_length=120)
    required_experience_years: Decimal | None = Field(
        default=None,
        ge=0,
        le=60,
        max_digits=5,
        decimal_places=2,
    )
    required_degrees: list[str] = Field(default_factory=list, max_length=50)
    required_skills: list[str] = Field(default_factory=list, max_length=100)
    salary_text: str | None = Field(default=None, max_length=500)
    salary_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    salary_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, max_length=8)
    salary_period: str | None = Field(default=None, max_length=40)
    description: str | None = None
    url: str | None = None
    published_at: datetime | None = None

    @field_validator("required_degrees", "required_skills", mode="before")
    @classmethod
    def clean_requirement_terms(cls, value: object) -> list[str]:
        return _clean_string_list(value)


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
