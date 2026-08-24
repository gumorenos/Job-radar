from decimal import Decimal

from app.db.enums import WorkMode
from app.domains.matching.fit import FitSignalInput, assess_career_move, evaluate_positive_fit


def _facts(**overrides: object) -> FitSignalInput:
    values: dict[str, object] = {
        "title": "Senior People Analytics Analyst",
        "description": "Lidera People Analytics, HR analytics y decisiones de gestión humana.",
        "location": "Lima",
        "work_mode": WorkMode.HYBRID,
        "monthly_salary_pen": Decimal("9000"),
        "target_roles": ("Senior Analyst", "HR Business Partner", "Manager"),
        "target_areas": ("People Analytics", "Gestión Humana"),
        "adjacent_areas": ("People Operations", "Employee Experience"),
    }
    values.update(overrides)
    return FitSignalInput(**values)  # type: ignore[arg-type]


def test_role_and_core_area_create_strong_positive_fit() -> None:
    result = evaluate_positive_fit(_facts())

    assert result.high_priority is True
    assert "Senior Analyst" in result.role_matches
    assert "People Analytics" in result.core_area_matches
    assert any("Rol objetivo" in strength for strength in result.strengths)
    assert any("Área foco" in strength for strength in result.strengths)
    assert assess_career_move(result).startswith("Movimiento alineado:")


def test_adjacent_area_stays_review_signal() -> None:
    result = evaluate_positive_fit(
        _facts(
            title="HR Business Partner",
            description="Responsable de People Operations y Employee Experience.",
        )
    )

    assert result.role_matches
    assert not result.core_area_matches
    assert result.adjacent_area_matches
    assert result.high_priority is False
    assert any("adyacente" in gap for gap in result.gaps)
    assert assess_career_move(result).startswith("Movimiento adyacente:")


def test_core_area_without_target_role_is_not_high_priority() -> None:
    result = evaluate_positive_fit(
        _facts(
            title="Consultor de transformación",
            description="Proyecto de People Analytics y gestión humana.",
        )
    )

    assert not result.role_matches
    assert result.core_area_matches
    assert result.high_priority is False
    assert assess_career_move(result).startswith("Área alineada con nivel por confirmar:")


def test_unknown_salary_does_not_erase_strong_fit() -> None:
    result = evaluate_positive_fit(_facts(monthly_salary_pen=None))

    assert result.high_priority is True
    assert any("salario no está publicado" in gap for gap in result.gaps)


def test_generic_manager_title_needs_hr_people_context_in_title() -> None:
    result = evaluate_positive_fit(
        _facts(
            title="Operations Manager",
            description=(
                "Lidera operaciones y participa con RRHH en iniciativas de People Analytics y "
                "gestión humana."
            ),
        )
    )

    assert not result.role_matches
    assert result.core_area_matches
    assert result.high_priority is False


def test_career_move_assessment_never_invents_candidate_history() -> None:
    result = evaluate_positive_fit(
        _facts(
            title="Analista de operaciones",
            description="Procesos generales sin foco de RRHH.",
            target_roles=("HR Business Partner",),
            target_areas=("People Analytics",),
            adjacent_areas=("People Operations",),
        )
    )

    assessment = assess_career_move(result)
    assert assessment.startswith("Movimiento no confirmado:")
    assert "años" not in assessment
    assert "experiencia" not in assessment
