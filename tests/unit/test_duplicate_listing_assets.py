from fastapi.testclient import TestClient

from app.main import app


def test_duplicate_listing_frontend_uses_server_search_and_pagination() -> None:
    with TestClient(app) as client:
        script = client.get("/app/duplicates.js")

    assert script.status_code == 200
    assert "duplicatePageSize = 50" in script.text
    assert 'offset: String(offset)' in script.text
    assert 'params.set("q", search)' in script.text
    assert 'id="duplicateLoadMore"' in script.text
    assert "loadDuplicateCandidates({ append: true })" in script.text
    assert "duplicateJobSearchText" not in script.text
