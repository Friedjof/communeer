from tests.conftest import login_as_admin as _login


def test_sync_route_returns_503_when_provider_is_unavailable(client, monkeypatch):
    """`sync_community` translating a transport failure into
    `WhatsAppProviderUnavailableError` (see `providers/whatsapp/wppconnect.py`)
    must surface as a clean 503 at `POST /communities/{id}/sync`, not the
    generic 500 an unguarded `httpx.HTTPError` used to produce."""
    import communeer.sync.router as sync_router_module
    from communeer.providers.whatsapp.base import WhatsAppProviderUnavailableError

    _login(client)
    unity_alpha = next(c for c in client.get("/api/v1/communities").json() if c["name"] == "Unity Alpha")

    def _raise_unavailable(*args, **kwargs):
        raise WhatsAppProviderUnavailableError("boom")

    monkeypatch.setattr(sync_router_module, "sync_community", _raise_unavailable)

    response = client.post(f"/api/v1/communities/{unity_alpha['id']}/sync")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


def test_sync_route_returns_409_when_a_sync_is_already_in_progress(client, monkeypatch):
    """`sync_community`'s `IntegrityError` -> `SyncInProgressError`
    translation (see `sync/service.py`, guarding against two overlapping
    syncs of the same community) must surface as a clean 409 at
    `POST /communities/{id}/sync`."""
    import communeer.sync.router as sync_router_module
    from communeer.sync.service import SyncInProgressError

    _login(client)
    unity_alpha = next(c for c in client.get("/api/v1/communities").json() if c["name"] == "Unity Alpha")

    def _raise_in_progress(*args, **kwargs):
        raise SyncInProgressError("already syncing")

    monkeypatch.setattr(sync_router_module, "sync_community", _raise_in_progress)

    response = client.post(f"/api/v1/communities/{unity_alpha['id']}/sync")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_unauthenticated_request_returns_401_envelope(client):
    response = client.get("/api/v1/communities")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert "message" in body["error"]


def test_login_sync_list_members_audit_flow(client):
    # unauthenticated -> 401
    assert client.get("/api/v1/session").status_code == 401

    # password step: the seeded admin has mandatory 2FA (owner role), so this
    # must come back as "requires TOTP", not a full session yet.
    login_response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "changeme123"})
    assert login_response.status_code == 200
    assert login_response.json()["requiresTotp"] is True
    assert "communeer_session" not in client.cookies

    # bad credentials -> 401, envelope shape, no cookie change
    bad_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad_login.status_code == 401
    assert bad_login.json()["error"]["code"] == "unauthorized"

    # TOTP step completes the login.
    _login(client)
    assert "communeer_session" in client.cookies

    # session reflects the logged-in user
    session_response = client.get("/api/v1/session")
    assert session_response.status_code == 200
    assert session_response.json()["username"] == "admin"

    # communities already primed at startup
    communities = client.get("/api/v1/communities")
    assert communities.status_code == 200
    community_names = {c["name"] for c in communities.json()}
    assert {"Unity Alpha", "Riverside Collective"} <= community_names

    unity_alpha = next(c for c in communities.json() if c["name"] == "Unity Alpha")
    assert "waId" in unity_alpha and "memberCount" in unity_alpha and "groupCount" in unity_alpha

    # explicit sync of Unity Alpha
    sync_response = client.post(f"/api/v1/communities/{unity_alpha['id']}/sync")
    assert sync_response.status_code == 200
    synced = sync_response.json()
    assert synced["name"] == "Unity Alpha"
    assert "description" in synced  # detail shape, not just summary

    # groups: Marketplace must show the spec's flagship 981/1024 numbers
    groups = client.get(f"/api/v1/communities/{unity_alpha['id']}/groups")
    assert groups.status_code == 200
    marketplace = next(g for g in groups.json() if g["name"] == "Marketplace")
    assert marketplace["memberCount"] == 981
    assert marketplace["memberLimit"] == 1024
    assert marketplace["pendingRequestCount"] == 3
    for key in ("description", "adminCount", "lastMessageAt"):
        assert key in marketplace
    assert marketplace["adminCount"] >= 0

    # community-wide member list
    members = client.get(f"/api/v1/communities/{unity_alpha['id']}/members")
    assert members.status_code == 200
    assert len(members.json()) > 0
    sample_member = members.json()[0]
    for key in ("id", "waId", "displayName", "isAdmin", "isCommunityAdmin", "groupCount"):
        assert key in sample_member

    # group members + requests
    group_members = client.get(f"/api/v1/groups/{marketplace['id']}/members")
    assert group_members.status_code == 200
    assert len(group_members.json()) == 981 + 3  # members + pending

    group_requests = client.get(f"/api/v1/groups/{marketplace['id']}/requests")
    assert group_requests.status_code == 200
    assert len(group_requests.json()) == 3
    for row in group_requests.json():
        assert set(row.keys()) == {"memberId", "waId", "displayName", "requestedAt"}

    # invite link: mock provider returns a deterministic (never `None`) fake link
    invite_link = client.get(f"/api/v1/groups/{marketplace['id']}/invite-link")
    assert invite_link.status_code == 200
    assert invite_link.json()["inviteLink"].startswith("https://chat.whatsapp.com/")

    # member detail, reached via one of the group members
    a_member_id = group_members.json()[0]["memberId"]
    member_detail = client.get(f"/api/v1/members/{a_member_id}")
    assert member_detail.status_code == 200
    assert "memberships" in member_detail.json()

    # audit trail recorded both the login and the sync
    audit = client.get("/api/v1/audit")
    assert audit.status_code == 200
    actions = {row["action"] for row in audit.json()}
    assert "auth.login" in actions
    assert "auth.login_failed" in actions
    assert "community.sync" in actions

    # logout clears the session
    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204
    assert client.get("/api/v1/session").status_code == 401


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


def test_viewer_role_gets_403_on_sync_but_owner_gets_200(client):
    _seed_viewer_user()

    # log in as owner first just to discover the community id, then log
    # back out before the viewer assertions.
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")
    client.post("/api/v1/auth/logout")

    # viewer role has no mandatory 2FA — a single-step login.
    viewer_login = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-123"})
    assert viewer_login.status_code == 200
    assert viewer_login.json()["role"] == "viewer"

    sync_response = client.post(f"/api/v1/communities/{unity_alpha['id']}/sync")
    assert sync_response.status_code == 403
    assert sync_response.json()["error"]["code"] == "forbidden"

    client.post("/api/v1/auth/logout")

    _login(client)
    assert client.post(f"/api/v1/communities/{unity_alpha['id']}/sync").status_code == 200


def test_advanced_query_param_includes_raw_metadata(client):
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")

    plain = client.get(f"/api/v1/communities/{unity_alpha['id']}")
    assert "rawMetadata" not in plain.json()

    advanced = client.get(f"/api/v1/communities/{unity_alpha['id']}", params={"advanced": "true"})
    assert "rawMetadata" in advanced.json()
    assert "isParentGroup" in advanced.json()["rawMetadata"]
