"""Endpoint tests for `whatsapp_status/router.py`, exercised against the
shared test app's `MockWhatsAppProvider` (the app-level `client`/`app`
fixtures from `conftest.py` — no dependency overrides needed since mock mode
is exactly what the shared test app already boots with).
"""


def _login(client) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "changeme123"})
    assert response.status_code == 200


def test_status_returns_connected_for_mock_provider(client):
    _login(client)

    response = client.get("/api/v1/whatsapp/status")

    assert response.status_code == 200
    body = response.json()
    assert body == {"state": "connected", "qrCodeDataUrl": None, "detail": None}


def test_connect_returns_400_for_mock_provider(client):
    _login(client)

    response = client.post("/api/v1/whatsapp/connect")

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "bad_request"
    assert "does not support" in body["error"]["message"]


def test_discover_and_sync_returns_synced_summaries_for_mock_provider(client):
    _login(client)

    response = client.post("/api/v1/whatsapp/discover-and-sync")

    assert response.status_code == 200
    body = response.json()
    names = {c["name"] for c in body}
    assert {"Unity Alpha", "Riverside Collective"} <= names
    for community in body:
        assert "waId" in community and "memberCount" in community


def test_status_requires_auth(client):
    response = client.get("/api/v1/whatsapp/status")
    assert response.status_code == 401


def test_connect_requires_auth(client):
    response = client.post("/api/v1/whatsapp/connect")
    assert response.status_code == 401


def test_discover_and_sync_requires_auth(client):
    response = client.post("/api/v1/whatsapp/discover-and-sync")
    assert response.status_code == 401
