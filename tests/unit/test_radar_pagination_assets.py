from fastapi.testclient import TestClient

from app.main import app


def test_radar_pagination_frontend_contract_is_served() -> None:
    with TestClient(app) as client:
        script = client.get("/app/duplicates.js")
        styles = client.get("/app/duplicates.css")

    assert script.status_code == 200
    assert "radarPageSize = 50" in script.text
    assert 'offset: String(offset)' in script.text
    assert 'id="radarLoadMore"' in script.text
    assert "Cargar más" in script.text
    assert "requestId !== radarPageRequestId" in script.text
    assert styles.status_code == 200
    assert ".radar-load-more" in styles.text
