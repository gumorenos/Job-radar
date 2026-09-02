from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cv_intelligence_ui_exposes_comparison_without_magic_score() -> None:
    script = (ROOT / "app" / "web" / "cvs.js").read_text()
    styles = (ROOT / "app" / "web" / "cvs.css").read_text()

    assert 'data-cv-action="compare"' in script
    assert "/comparison" in script
    assert "Revisar evidencia antes de aprobar" in script
    assert "se muestran como señales, no como un score" in script
    assert "ATS score" not in script
    assert ".cv-comparison-panel" in styles
    assert ".cv-claim-warning" in styles


def test_structured_fit_ui_uses_saved_analyzer_version_instead_of_stale_literal() -> None:
    script = (ROOT / "app" / "web" / "structured_fit.js").read_text()

    assert "analysis.analyzer_version" in script
    assert "analysis.rule_results?.analyzer_version" in script
    assert '"rules-v5"' not in script
