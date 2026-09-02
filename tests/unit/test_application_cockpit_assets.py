from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_application_ui_exposes_next_action_follow_up_and_timeline_controls() -> None:
    script = (ROOT / "app" / "web" / "applications.js").read_text()
    styles = (ROOT / "app" / "web" / "applications.css").read_text()

    assert "data-save-plan" in script
    assert "data-follow-up-complete" in script
    assert "follow-up-complete" in script
    assert "/timeline" in script
    assert "opportunity-cockpit" in script
    assert "Siguiente paso" in script
    assert "baseLoadJobDetail" in script
    assert "alreadySynchronized" in script
    assert ".application-plan.overdue" in styles
    assert ".opportunity-cockpit" in styles
