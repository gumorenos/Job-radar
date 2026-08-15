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
    assert 'src="/app/applications.js"' in response.text
    assert 'href="/app/applications.css"' in response.text
    assert 'id="applicationsList"' in response.text
    assert "prototype-note" not in response.text


def test_application_shell_serves_frontend_assets() -> None:
    with TestClient(app) as client:
        favicon = client.get("/app/favicon.svg")
        applications_js = client.get("/app/applications.js")
        applications_css = client.get("/app/applications.css")

    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert applications_js.status_code == 200
    assert "add_job_to_applications" not in applications_js.text
    assert "Añadir a postulaciones" in applications_js.text
    assert applications_css.status_code == 200
    assert ".application-row" in applications_css.text
