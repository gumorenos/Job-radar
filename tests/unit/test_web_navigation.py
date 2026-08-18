from fastapi.testclient import TestClient

from app.main import app


def test_application_shell_exposes_simplified_primary_navigation() -> None:
    with TestClient(app) as client:
        response = client.get("/app/")

    assert response.status_code == 200
    assert "Radar" in response.text
    assert "Postulaciones" in response.text
    assert "CVs" in response.text
    assert "Configuración" in response.text
    assert "Correr radar" not in response.text
    assert "Perfil JSON" not in response.text
    assert 'id="opportunitySearch"' in response.text
    assert 'name="opportunity_search"' in response.text
    assert 'href="/app/favicon.svg"' in response.text
    assert 'id="profileSettingsForm"' in response.text
    assert 'id="salaryMinPen"' in response.text
    assert 'id="targetRoles"' in response.text
    assert 'src="/app/settings.js"' in response.text


def test_application_shell_serves_settings_assets() -> None:
    with TestClient(app) as client:
        favicon = client.get("/app/favicon.svg")
        settings_script = client.get("/app/settings.js")
        settings_styles = client.get("/app/settings.css")

    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert settings_script.status_code == 200
    assert "loadProfileSettings" in settings_script.text
    assert settings_styles.status_code == 200
    assert ".profile-settings" in settings_styles.text
