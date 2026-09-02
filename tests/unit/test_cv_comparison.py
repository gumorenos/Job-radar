from app.domains.cvs.comparison import CvSkillSignal, compare_cv_text, required_skill_signals


def test_cv_comparison_tracks_replaced_added_removed_and_quality_signals() -> None:
    parent = """People Analytics specialist.
Built dashboards for HR leaders.
Managed onboarding."""
    current = """People Analytics specialist.
Built 12 dashboards for HR leaders and reduced reporting time 30%.
Automated onboarding with Power BI.
Led workforce planning."""

    result = compare_cv_text(parent, current)

    assert result.parent_word_count > 0
    assert result.current_word_count > result.parent_word_count
    assert result.quantified_statement_count == 1
    assert result.unchanged_count == 1
    assert any(item.kind == "REPLACED" for item in result.changes)
    assert any(item.kind == "ADDED" for item in result.changes)


def test_required_skill_signals_are_case_insensitive_without_single_score() -> None:
    signals = required_skill_signals(
        ["Power BI", "Workforce Planning", "Power BI"],
        "Experiencia con power bi y automatización de RRHH.",
    )

    assert signals == [
        CvSkillSignal(skill="Power BI", present=True),
        CvSkillSignal(skill="Workforce Planning", present=False),
    ]
