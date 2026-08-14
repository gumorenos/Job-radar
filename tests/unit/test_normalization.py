from app.db.enums import WorkMode
from app.domains.jobs.normalization import (
    comparison_key,
    is_confidential_company,
    normalize_url,
    normalize_work_mode,
)


def test_url_normalization_removes_tracking_parameters() -> None:
    url = "https://Example.com/jobs/123/?utm_source=email&trackingId=abc&foo=bar#apply"
    assert normalize_url(url) == "https://example.com/jobs/123?foo=bar"


def test_company_confidential_detection_is_accent_and_case_tolerant() -> None:
    assert is_confidential_company("Empresa Confidencial") is True
    assert is_confidential_company("ACME") is False


def test_work_mode_normalization() -> None:
    assert normalize_work_mode("100% Remoto LATAM") == WorkMode.REMOTE
    assert normalize_work_mode("Híbrido") == WorkMode.HYBRID
    assert normalize_work_mode("Presencial") == WorkMode.ONSITE


def test_comparison_key_normalizes_accents_and_punctuation() -> None:
    assert comparison_key("Gestión  Humana / Perú") == "gestion humana peru"
