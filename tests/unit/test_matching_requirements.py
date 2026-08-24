from decimal import Decimal

from app.domains.matching.requirements import (
    RequirementStatus,
    assess_degree,
    assess_experience,
    assess_skills,
    assess_structured_fit,
)


def test_experience_gap_of_two_years_is_partial_review_not_discard() -> None:
    result = assess_experience(Decimal("5"), Decimal("7"))

    assert result.status == RequirementStatus.PARTIALLY
    assert result.requires_review is True
    assert "5" in result.message
    assert "7" in result.message


def test_experience_meets_requirement() -> None:
    result = assess_experience(Decimal("7"), Decimal("5"))

    assert result.status == RequirementStatus.MEETS
    assert result.requires_review is False


def test_degree_mismatch_is_possible_exclusion_review() -> None:
    result = assess_degree(("Administración",), ("Psicología",))

    assert result.status == RequirementStatus.POSSIBLE_EXCLUSION
    assert result.requires_review is True


def test_degree_unknown_profile_does_not_invent_mismatch() -> None:
    result = assess_degree((), ("Psicología",))

    assert result.status == RequirementStatus.UNKNOWN
    assert result.requires_review is False


def test_transferable_skills_can_cover_all_requirements_without_forcing_review() -> None:
    assessment, items = assess_skills(
        ("People Analytics",),
        ("Power BI",),
        ("People Analytics", "Power BI"),
    )

    assert assessment.status == RequirementStatus.TRANSFERABLE
    assert assessment.requires_review is False
    assert [item.status for item in items] == [
        RequirementStatus.MEETS,
        RequirementStatus.TRANSFERABLE,
    ]


def test_partial_skills_force_review() -> None:
    assessment, items = assess_skills(
        ("People Analytics",),
        (),
        ("People Analytics", "SAP SuccessFactors"),
    )

    assert assessment.status == RequirementStatus.PARTIALLY
    assert assessment.requires_review is True
    assert items[1].status == RequirementStatus.DOES_NOT_MEET


def test_structured_fit_aggregates_review_without_hard_discard_semantics() -> None:
    result = assess_structured_fit(
        candidate_experience_years=Decimal("5"),
        candidate_degrees=("Administración",),
        candidate_skills=("People Analytics",),
        transferable_skills=("Power BI",),
        required_experience_years=Decimal("7"),
        required_degrees=("Administración",),
        required_skills=("People Analytics", "Power BI"),
    )

    assert result.experience.status == RequirementStatus.PARTIALLY
    assert result.degree.status == RequirementStatus.MEETS
    assert result.skills.status == RequirementStatus.TRANSFERABLE
    assert result.requires_review is True
    assert result.as_dict()["requires_review"] is True
