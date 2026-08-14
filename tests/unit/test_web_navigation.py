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


def test_application_shell_serves_favicon() -> None:
    with TestClient(app) as client:
        response = client.get("/app/favicon.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
