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
    assert 'id="cvGrid"' in response.text
    assert 'id="addCvButton"' in response.text
    assert 'src="/app/cvs.js"' in response.text


def test_application_shell_serves_static_assets() -> None:
    with TestClient(app) as client:
        favicon = client.get("/app/favicon.svg")
        cvs_script = client.get("/app/cvs.js")

    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert cvs_script.status_code == 200
    assert "loadCvs" in cvs_script.text
