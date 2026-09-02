from decimal import Decimal

import pytest

from app.db.enums import Classification, WorkMode
from app.domains.matching.rules import (
    HardRuleToggles,
    MatchingRuleInput,
    MatchingRulePolicy,
    evaluate_business_rules,
    hard_rule_toggles_from_metadata,
    with_hard_rule_toggles,
)


@pytest.mark.parametrize(
    "title",
    [
        "Practicante de Recursos Humanos",
        "HR Assistant",
        "Analista Junior de Gestión Humana",
    ],
)
def test_excluded_seniority_titles_force_discard(title: str) -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(title=title, location="Lima", work_mode=WorkMode.HYBRID)
    )

    assert result.forced_classification == Classification.DISCARD


def test_disabled_seniority_hard_rule_does_not_force_discard() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="HR Assistant",
            location="Lima",
            work_mode=WorkMode.HYBRID,
        ),
        MatchingRulePolicy(
            hard_rules=HardRuleToggles(discard_disallowed_titles=False),
        ),
    )

    assert result.forced_classification is None
    seniority = next(item for item in result.results if item.code == "SENIORITY_TITLE")
    assert seniority.enabled is False
    assert seniority.severity == "INFO"
    assert seniority.passed is True


def test_onsite_outside_lima_forces_discard() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="HR Business Partner",
            location="Arequipa, Perú",
            work_mode=WorkMode.ONSITE,
        )
    )

    assert result.forced_classification == Classification.DISCARD


def test_disabled_onsite_location_hard_rule_does_not_force_discard() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="HR Business Partner",
            location="Arequipa, Perú",
            work_mode=WorkMode.ONSITE,
        ),
        MatchingRulePolicy(
            hard_rules=HardRuleToggles(discard_onsite_outside_lima=False),
        ),
    )

    assert result.forced_classification is None
    location = next(item for item in result.results if item.code == "ONSITE_LOCATION")
    assert location.enabled is False
    assert location.severity == "INFO"


@pytest.mark.parametrize(
    "location",
    [
        "San Isidro, Lima",
        "Ate, Lima",
        "Los Olivos, Lima",
        "San Juan de Lurigancho",
        "Villa El Salvador",
        "Ventanilla, Callao",
    ],
)
def test_onsite_lima_metropolitana_is_allowed(location: str) -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="HR Business Partner",
            location=location,
            work_mode=WorkMode.ONSITE,
        )
    )

    assert result.forced_classification is None


def test_unknown_salary_does_not_discard() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="People Analytics Lead",
            location="Lima",
            work_mode=WorkMode.HYBRID,
            monthly_salary_pen=None,
        )
    )

    assert result.forced_classification is None
    assert result.requires_review is False


def test_published_salary_without_safe_pen_conversion_requires_review() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="People Analytics Lead",
            location="Remote LATAM",
            work_mode=WorkMode.REMOTE,
            monthly_salary_pen=None,
            salary_published_unassessed=True,
            is_international_remote=True,
        )
    )

    assert result.forced_classification is None
    assert result.requires_review is True
    salary = next(item for item in result.results if item.code == "PUBLISHED_SALARY")
    assert salary.severity == "WARNING"


def test_local_published_salary_below_7000_forces_discard() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="People Analytics Lead",
            location="Lima",
            work_mode=WorkMode.HYBRID,
            monthly_salary_pen=Decimal("6999"),
        )
    )

    assert result.forced_classification == Classification.DISCARD


def test_disabled_salary_hard_rule_does_not_force_discard() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="People Analytics Lead",
            location="Lima",
            work_mode=WorkMode.HYBRID,
            monthly_salary_pen=Decimal("5000"),
        ),
        MatchingRulePolicy(
            hard_rules=HardRuleToggles(discard_published_salary_below_floor=False),
        ),
    )

    assert result.forced_classification is None
    assert result.requires_review is False
    salary = next(item for item in result.results if item.code == "PUBLISHED_SALARY")
    assert salary.enabled is False
    assert salary.severity == "INFO"
    assert "desactivada" in salary.message


def test_remote_international_salary_uses_7700_floor() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="Strategic HRBP",
            location="LATAM",
            work_mode=WorkMode.REMOTE,
            monthly_salary_pen=Decimal("7500"),
            is_international_remote=True,
        )
    )

    assert result.forced_classification == Classification.DISCARD


def test_agriculture_is_review_warning_not_discard() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="HR Manager",
            location="Lima",
            work_mode=WorkMode.HYBRID,
            industry="Agroindustrial",
        )
    )

    assert result.forced_classification is None
    assert result.requires_review is True


def test_degree_mismatch_and_experience_gap_are_warnings() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="Senior HR Business Partner",
            location="Lima",
            work_mode=WorkMode.HYBRID,
            degree_mismatch=True,
            degree_is_required=True,
            requested_years_experience=7,
            candidate_years_experience=5,
        )
    )

    assert result.forced_classification is None
    assert result.requires_review is True
    warning_codes = {item.code for item in result.results if item.severity == "WARNING"}
    assert warning_codes == {"DEGREE_MISMATCH", "EXPERIENCE_GAP"}


def test_legacy_profile_metadata_keeps_all_hard_rules_enabled() -> None:
    toggles = hard_rule_toggles_from_metadata({"source": "legacy"})

    assert toggles == HardRuleToggles()


def test_hard_rule_metadata_round_trip_preserves_unrelated_metadata() -> None:
    metadata = with_hard_rule_toggles(
        {"source": "phase-0-confirmed-rules", "future": {"keep": True}},
        HardRuleToggles(
            discard_disallowed_titles=False,
            discard_onsite_outside_lima=True,
            discard_published_salary_below_floor=False,
        ),
    )

    assert metadata["source"] == "phase-0-confirmed-rules"
    assert metadata["future"] == {"keep": True}
    assert hard_rule_toggles_from_metadata(metadata) == HardRuleToggles(
        discard_disallowed_titles=False,
        discard_onsite_outside_lima=True,
        discard_published_salary_below_floor=False,
    )
