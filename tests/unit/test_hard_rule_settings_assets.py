from fastapi.testclient import TestClient

from app.main import app


HARD_RULE_IDS = (
    "hardRuleSeniority",
    "hardRuleOnsiteOutsideLima",
    "hardRuleSalaryFloor",
)
HARD_RULE_KEYS = (
    "discard_disallowed_titles",
    "discard_onsite_outside_lima",
    "discard_published_salary_below_floor",
)


def test_settings_exposes_only_explicit_hard_rule_controls() -> None:
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/app/settings.js")

    assert page.status_code == 200
    assert script.status_code == 200
    for control_id in HARD_RULE_IDS:
        assert f'id="{control_id}"' in page.text
        assert f'getElementById("{control_id}")' in script.text
    for key in HARD_RULE_KEYS:
        assert key in page.text
        assert key in script.text
    assert "Una sugerencia de IA nunca se activa sola" in page.text
    assert "hard_rules:" in script.text
