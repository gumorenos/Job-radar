from decimal import Decimal

import pytest

from app.db.enums import Classification, WorkMode
from app.domains.matching.rules import MatchingRuleInput, evaluate_business_rules


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


def test_onsite_outside_lima_forces_discard() -> None:
    result = evaluate_business_rules(
        MatchingRuleInput(
            title="HR Business Partner",
            location="Arequipa, Perú",
            work_mode=WorkMode.ONSITE,
        )
    )

    assert result.forced_classification == Classification.DISCARD


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
