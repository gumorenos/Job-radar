from datetime import UTC, datetime
from decimal import Decimal

from app.db.enums import JobStatus, PostingStatus, WorkMode
from app.db.models import Job, JobPosting
from app.domains.matching.facts import (
    is_international_remote,
    monthly_salary_pen,
    published_salary_unassessed,
)


def _posting(**overrides: object) -> JobPosting:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "job_id": None,
        "first_seen_at": now,
        "last_seen_at": now,
        "posting_status": PostingStatus.ACTIVE,
    }
    values.update(overrides)
    return JobPosting(**values)  # type: ignore[arg-type]


def _job(**overrides: object) -> Job:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "canonical_title": "HR Business Partner",
        "location_text": "Lima",
        "work_mode": WorkMode.REMOTE,
        "status": JobStatus.ACTIVE,
        "first_seen_at": now,
        "last_seen_at": now,
    }
    values.update(overrides)
    return Job(**values)  # type: ignore[arg-type]


def test_salary_text_parses_pen_monthly_amount() -> None:
    assert monthly_salary_pen(_posting(salary_text="S/ 8,500")) == Decimal("8500")


def test_salary_range_uses_upper_bound_conservatively() -> None:
    assert monthly_salary_pen(_posting(salary_text="S/ 6,000 - S/ 8,000")) == Decimal("8000")


def test_annual_pen_salary_is_converted_to_monthly() -> None:
    assert monthly_salary_pen(_posting(salary_text="PEN 84,000 anual")) == Decimal("7000")


def test_non_pen_salary_is_not_guessed_and_is_marked_unassessed() -> None:
    posting = _posting(salary_text="USD 2,000 monthly")

    assert monthly_salary_pen(posting) is None
    assert published_salary_unassessed(posting) is True


def test_text_without_numeric_salary_is_not_marked_unassessed() -> None:
    assert published_salary_unassessed(_posting(salary_text="Competitive")) is False


def test_latam_remote_is_international() -> None:
    assert is_international_remote(_job(location_text="Remote LATAM")) is True


def test_latam_remote_wins_over_platform_country_peru() -> None:
    assert is_international_remote(
        _job(location_text="Remote LATAM", country="Peru")
    ) is True


def test_remote_peru_is_not_international() -> None:
    assert is_international_remote(_job(location_text="Remote - Perú")) is False
