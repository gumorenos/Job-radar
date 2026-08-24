from fastapi.testclient import TestClient

from app.main import app


def test_notification_inbox_frontend_uses_incremental_pagination() -> None:
    with TestClient(app) as client:
        script = client.get("/app/notifications.js")
        styles = client.get("/app/notifications.css")

    assert script.status_code == 200
    assert "notificationPageSize = 40" in script.text
    assert "offset: String(offset)" in script.text
    assert 'id="notificationLoadMore"' in script.text
    assert "loadInbox({ append: true })" in script.text
    assert "requestId !== inboxRequestId" in script.text
    assert styles.status_code == 200
    assert ".notification-load-more" in styles.text
