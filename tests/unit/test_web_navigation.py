from fastapi.testclient import TestClient

from app.main import app


def test_application_shell_exposes_complete_core_navigation() -> None:
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
    assert 'src="/app/structured_fit.js"' in response.text
    assert 'src="/app/duplicates.js"' in response.text
    assert 'src="/app/applications.js"' in response.text
    assert 'src="/app/cvs.js"' in response.text
    assert 'src="/app/settings.js"' in response.text
    assert 'src="/app/notifications.js"' in response.text
    assert 'href="/app/duplicates.css"' in response.text
    assert 'href="/app/applications.css"' in response.text
    assert 'href="/app/settings.css"' in response.text
    assert 'id="applicationsList"' in response.text
    assert 'id="cvGrid"' in response.text
    assert 'id="profileSettingsForm"' in response.text
    assert "prototype-note" not in response.text


def test_application_shell_serves_core_frontend_assets() -> None:
    with TestClient(app) as client:
        favicon = client.get("/app/favicon.svg")
        styles = client.get("/app/styles.css")
        structured_fit_js = client.get("/app/structured_fit.js")
        structured_fit_css = client.get("/app/structured_fit.css")
        duplicates_js = client.get("/app/duplicates.js")
        duplicates_css = client.get("/app/duplicates.css")
        applications_js = client.get("/app/applications.js")
        applications_css = client.get("/app/applications.css")
        cvs_js = client.get("/app/cvs.js")
        cvs_css = client.get("/app/cvs.css")
        settings_js = client.get("/app/settings.js")
        settings_css = client.get("/app/settings.css")
        notifications_js = client.get("/app/notifications.js")
        notifications_css = client.get("/app/notifications.css")

    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert styles.status_code == 200
    assert ".summary-strip," in styles.text
    assert "z-index: 26;" in styles.text
    assert structured_fit_js.status_code == 200
    assert "Requisitos vs perfil" in structured_fit_js.text
    assert "POSSIBLE_EXCLUSION" in structured_fit_js.text
    assert "structured_fit" in structured_fit_js.text
    assert structured_fit_css.status_code == 200
    assert ".structured-fit-section" in structured_fit_css.text
    assert ".fit-status.transferable" in structured_fit_css.text
    assert duplicates_js.status_code == 200
    assert "Mantener separadas" in duplicates_js.text
    assert duplicates_css.status_code == 200
    assert ".duplicate-row" in duplicates_css.text
    assert applications_js.status_code == 200
    assert "Añadir a postulaciones" in applications_js.text
    assert applications_css.status_code == 200
    assert ".application-row" in applications_css.text
    assert cvs_js.status_code == 200
    assert "Nueva versión" in cvs_js.text
    assert cvs_css.status_code == 200
    assert ".cv-dialog" in cvs_css.text
    assert settings_js.status_code == 200
    assert "/api/v1/profile" in settings_js.text
    assert settings_css.status_code == 200
    assert ".profile-settings" in settings_css.text
    assert notifications_js.status_code == 200
    assert "/api/v1/notifications/inbox" in notifications_js.text
    assert "notificationDrawer" in notifications_js.text
    assert notifications_css.status_code == 200
    assert ".notification-drawer" in notifications_css.text
