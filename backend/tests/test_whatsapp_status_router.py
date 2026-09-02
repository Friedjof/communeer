"""Endpoint tests for `whatsapp_status/router.py`, exercised against the
shared test app's `MockWhatsAppProvider` (the app-level `client`/`app`
fixtures from `conftest.py` — no dependency overrides needed since mock mode
is exactly what the shared test app already boots with).
"""

from tests.conftest import login_as_admin as _login


def test_status_returns_connected_for_mock_provider(client):
    _login(client)

    response = client.get("/api/v1/whatsapp/status")

    assert response.status_code == 200
    body = response.json()
    assert body == {"state": "connected", "qrCodeDataUrl": None, "detail": None, "discoveryInProgress": False}


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
    communities = body["communities"]
    names = {c["name"] for c in communities}
    assert {"Unity Alpha", "Riverside Collective"} <= names
    for community in communities:
        assert "waId" in community and "memberCount" in community
    # `MockWhatsAppProvider.get_admin_community_wa_ids()` always returns
    # `None` (no "connected account" concept) — nothing is ever hidden or
    # reported as failed in mock mode.
    assert body["hiddenNonAdminWaIds"] == []
    assert body["failed"] == []


def test_discover_and_sync_reports_hidden_non_admin_communities(client, monkeypatch):
    """A community that synced successfully but where the connected
    WhatsApp number isn't an admin must still be listed in `communities`
    (unfiltered — `GET /communities` is what actually hides it) but flagged
    in `hiddenNonAdminWaIds`, so the Setup page can say so honestly instead
    of it just silently never showing up anywhere (see `discover_and_sync`'s
    comment on this)."""
    from communeer.providers.whatsapp.mock import MockWhatsAppProvider

    _login(client)

    unity_wa_id = "120363010000000001@g.us"
    riverside_wa_id = "120363020000000001@g.us"
    monkeypatch.setattr(
        MockWhatsAppProvider, "get_admin_community_wa_ids", lambda self: {unity_wa_id}
    )

    response = client.post("/api/v1/whatsapp/discover-and-sync")

    assert response.status_code == 200
    body = response.json()
    assert body["hiddenNonAdminWaIds"] == [riverside_wa_id]
    synced_wa_ids = {c["waId"] for c in body["communities"]}
    assert {unity_wa_id, riverside_wa_id} <= synced_wa_ids


def test_discover_and_sync_returns_503_when_provider_is_unavailable(client, monkeypatch):
    """A transport failure translated into `WhatsAppProviderUnavailableError`
    (see `providers/whatsapp/wppconnect.py`) must surface as a clean 503 at
    `POST /whatsapp/discover-and-sync`, not the generic 500 an unguarded
    `httpx.HTTPError` used to produce."""
    import communeer.whatsapp_status.router as whatsapp_status_router_module
    from communeer.providers.whatsapp.base import WhatsAppProviderUnavailableError

    _login(client)

    def _raise_unavailable(*args, **kwargs):
        raise WhatsAppProviderUnavailableError("boom")

    monkeypatch.setattr(whatsapp_status_router_module, "sync_community", _raise_unavailable)

    response = client.post("/api/v1/whatsapp/discover-and-sync")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


def test_discover_and_sync_continues_past_one_communitys_failure(client, monkeypatch):
    """One community failing (e.g. a transient WPPConnect timeout while
    hydrating just that one) must not discard every other community's
    already-committed sync — the whole point of isolating each community in
    its own try/except (see `discover_and_sync`'s comment). Only the failing
    community's `wa_id` is made to raise; the real `sync_community` still
    runs for every other one from the mock fixture."""
    import communeer.whatsapp_status.router as whatsapp_status_router_module
    from communeer.providers.whatsapp.base import WhatsAppProviderUnavailableError
    from communeer.sync.service import sync_community as real_sync_community

    _login(client)

    unity_wa_id = "120363010000000001@g.us"

    def _fail_only_unity(db, provider, community_wa_id, **kwargs):
        if community_wa_id == unity_wa_id:
            raise WhatsAppProviderUnavailableError("boom")
        return real_sync_community(db, provider, community_wa_id, **kwargs)

    monkeypatch.setattr(whatsapp_status_router_module, "sync_community", _fail_only_unity)

    response = client.post("/api/v1/whatsapp/discover-and-sync")

    assert response.status_code == 200
    body = response.json()
    communities = body["communities"]
    names = {c["name"] for c in communities}
    assert "Riverside Collective" in names
    assert "Unity Alpha" not in names

    # The failed community is reported, with a safe generic reason —
    # never the raw exception text (see `_discovery_failure_reason`).
    assert len(body["failed"]) == 1
    assert body["failed"][0]["waId"] == unity_wa_id
    assert body["failed"][0]["name"] == "Unity Alpha"
    assert "boom" not in body["failed"][0]["reason"]

    # The failed community's provisioning reconciliation etc. never even ran
    # (its sync raised before committing), but the flag must still reset
    # cleanly for a follow-up retry.
    status_response = client.get("/api/v1/whatsapp/status")
    assert status_response.json()["discoveryInProgress"] is False


def test_discover_and_sync_returns_409_when_a_sync_is_already_in_progress(client, monkeypatch):
    """`sync_community`'s `IntegrityError` -> `SyncInProgressError`
    translation (see `sync/service.py`) must surface as a clean 409 at
    `POST /whatsapp/discover-and-sync`."""
    import communeer.whatsapp_status.router as whatsapp_status_router_module
    from communeer.sync.service import SyncInProgressError

    _login(client)

    def _raise_in_progress(*args, **kwargs):
        raise SyncInProgressError("already syncing")

    monkeypatch.setattr(whatsapp_status_router_module, "sync_community", _raise_in_progress)

    response = client.post("/api/v1/whatsapp/discover-and-sync")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_discover_and_sync_returns_409_when_a_discovery_is_already_in_progress(client, monkeypatch):
    """The module-level `_discovery_in_progress` flag (see
    `whatsapp_status/router.py`) must reject a second, overlapping discovery
    outright rather than racing the first — this is the guard a reloaded
    page relies on not clicking through by accident."""
    import communeer.whatsapp_status.router as whatsapp_status_router_module

    _login(client)
    monkeypatch.setattr(whatsapp_status_router_module, "_discovery_in_progress", True)

    response = client.post("/api/v1/whatsapp/discover-and-sync")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_discover_and_sync_flag_resets_after_success(client):
    _login(client)

    client.post("/api/v1/whatsapp/discover-and-sync")

    status_response = client.get("/api/v1/whatsapp/status")
    assert status_response.json()["discoveryInProgress"] is False


def test_discover_and_sync_flag_resets_after_failure(client, monkeypatch):
    """The flag must be cleared in a `finally` — a failed discovery must not
    permanently lock out every future attempt."""
    import communeer.whatsapp_status.router as whatsapp_status_router_module
    from communeer.providers.whatsapp.base import WhatsAppProviderUnavailableError

    _login(client)

    def _raise_unavailable(*args, **kwargs):
        raise WhatsAppProviderUnavailableError("boom")

    monkeypatch.setattr(whatsapp_status_router_module, "sync_community", _raise_unavailable)
    failed_response = client.post("/api/v1/whatsapp/discover-and-sync")
    assert failed_response.status_code == 503

    status_response = client.get("/api/v1/whatsapp/status")
    assert status_response.json()["discoveryInProgress"] is False


def test_status_requires_auth(client):
    response = client.get("/api/v1/whatsapp/status")
    assert response.status_code == 401


def test_connect_requires_auth(client):
    response = client.post("/api/v1/whatsapp/connect")
    assert response.status_code == 401


def test_discover_and_sync_requires_auth(client):
    response = client.post("/api/v1/whatsapp/discover-and-sync")
    assert response.status_code == 401


def _seed_viewer_user() -> None:
    """Creates a `viewer`-role user directly via the DB, bypassing the
    normal (owner-only, not yet built) user-management flow — same pattern
    used in `test_moderation.py`."""
    from sqlalchemy import select

    from communeer.auth.security import hash_password
    from communeer.db import SessionLocal
    from communeer.models import User, UserRole

    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.username == "viewer")).scalar_one_or_none()
        if existing is not None:
            return
        db.add(
            User(
                username="viewer",
                password_hash=hash_password("viewer-password-123"),
                role=UserRole.viewer,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()


def test_viewer_role_gets_403_on_connect_and_discover_and_sync_but_owner_gets_through(client):
    _seed_viewer_user()

    viewer_login = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-123"})
    assert viewer_login.status_code == 200
    assert viewer_login.json()["role"] == "viewer"

    connect_response = client.post("/api/v1/whatsapp/connect")
    assert connect_response.status_code == 403
    assert connect_response.json()["error"]["code"] == "forbidden"

    discover_response = client.post("/api/v1/whatsapp/discover-and-sync")
    assert discover_response.status_code == 403
    assert discover_response.json()["error"]["code"] == "forbidden"

    client.post("/api/v1/auth/logout")
    _login(client)

    # owner still gets the mock provider's normal (non-403) responses.
    assert client.post("/api/v1/whatsapp/connect").status_code == 400
    assert client.post("/api/v1/whatsapp/discover-and-sync").status_code == 200
