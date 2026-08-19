from datetime import UTC, datetime, time
from decimal import Decimal

from app.db.models import CandidateProfile
from app.domains.notifications.service import next_daily_review_at


def _profile() -> CandidateProfile:
    return CandidateProfile(
        name="Perfil",
        salary_min_pen=Decimal("7000"),
        remote_salary_multiplier=Decimal("1.10"),
        target_locations=[],
        target_roles=[],
        target_areas=[],
        adjacent_areas=[],
        rules={},
        daily_review_time=time(21, 0),
        timezone="America/Lima",
    )


def test_daily_review_uses_profile_timezone_same_day_when_still_pending() -> None:
    result = next_daily_review_at(
        _profile(),
        now=datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
    )

    assert result == datetime(2026, 8, 19, 2, 0, tzinfo=UTC)


def test_daily_review_rolls_to_next_day_after_local_cutoff() -> None:
    result = next_daily_review_at(
        _profile(),
        now=datetime(2026, 8, 19, 3, 0, tzinfo=UTC),
    )

    assert result == datetime(2026, 8, 20, 2, 0, tzinfo=UTC)


def test_unknown_profile_timezone_falls_back_to_utc() -> None:
    profile = _profile()
    profile.timezone = "Not/AZone"

    result = next_daily_review_at(
        profile,
        now=datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
    )

    assert result == datetime(2026, 8, 18, 21, 0, tzinfo=UTC)
