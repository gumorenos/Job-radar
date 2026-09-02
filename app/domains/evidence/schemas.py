from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import EvidenceSourceType, EvidenceVerificationStatus


def _clean_tags(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("tags debe ser una lista.")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            raise ValueError("Cada tag debe ser texto.")
        tag = raw.strip()
        if not tag:
            continue
        if len(tag) > 80:
            raise ValueError("Cada tag debe tener como máximo 80 caracteres.")
        key = tag.casefold()
        if key not in seen:
            cleaned.append(tag)
            seen.add(key)
    if len(cleaned) > 50:
        raise ValueError("Se permiten como máximo 50 tags.")
    return cleaned


class CareerEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=5000)
    category: str = Field(default="OTHER", min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list)
    source_type: EvidenceSourceType = EvidenceSourceType.MANUAL
    generated_by_ai: bool = False
    source_reference: str | None = Field(default=None, max_length=2000)
    source_excerpt: str | None = Field(default=None, max_length=8000)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("statement", "category")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El texto no puede estar vacío.")
        return cleaned

    @field_validator("source_reference", "source_excerpt", "notes")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("tags", mode="before")
    @classmethod
    def clean_tags(cls, value: object) -> list[str]:
        return _clean_tags(value)


class CareerEvidenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str | None = Field(default=None, min_length=1, max_length=5000)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    tags: list[str] | None = None
    source_reference: str | None = Field(default=None, max_length=2000)
    source_excerpt: str | None = Field(default=None, max_length=8000)
    source_metadata: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("statement", "category")
    @classmethod
    def clean_optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El texto no puede estar vacío.")
        return cleaned

    @field_validator("source_reference", "source_excerpt", "notes")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("tags", mode="before")
    @classmethod
    def clean_tags(cls, value: object) -> list[str] | None:
        if value is None:
            return None
        return _clean_tags(value)


class EvidenceVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EvidenceVerificationStatus
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CareerEvidenceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_profile_id: UUID
    statement: str
    category: str
    tags: list[str]
    source_type: EvidenceSourceType
    verification_status: EvidenceVerificationStatus
    generated_by_ai: bool
    source_reference: str | None
    source_excerpt: str | None
    source_metadata: dict[str, Any]
    notes: str | None
    reviewed_at: datetime | None
    verified_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CareerEvidenceList(BaseModel):
    items: list[CareerEvidenceView]
    total: int
    limit: int
    offset: int
