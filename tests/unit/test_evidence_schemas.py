from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.db.enums import EvidenceSourceType, EvidenceVerificationStatus
from app.domains.evidence.schemas import CareerEvidenceCreate, EvidenceVerificationRequest


def test_evidence_create_normalizes_tags_and_text() -> None:
    payload = CareerEvidenceCreate(
        statement="  Gestioné un proceso regional de onboarding.  ",
        category="  ONBOARDING  ",
        tags=["Onboarding", " onboarding ", "Scale", ""],
        source_type=EvidenceSourceType.USER_INTERVIEW,
    )

    assert payload.statement == "Gestioné un proceso regional de onboarding."
    assert payload.category == "ONBOARDING"
    assert payload.tags == ["Onboarding", "Scale"]
    assert payload.source_type == EvidenceSourceType.USER_INTERVIEW


def test_evidence_create_rejects_too_many_tags() -> None:
    with pytest.raises(ValidationError):
        CareerEvidenceCreate(
            statement="Evidencia",
            tags=[f"tag-{index}" for index in range(51)],
        )


def test_verification_supports_user_cannot_confirm() -> None:
    payload = EvidenceVerificationRequest(
        status=EvidenceVerificationStatus.USER_CANNOT_CONFIRM,
        notes="La magnitud exacta no se recuerda con seguridad.",
    )

    assert payload.status == EvidenceVerificationStatus.USER_CANNOT_CONFIRM
