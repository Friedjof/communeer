def test_unauthenticated_request_returns_401_envelope(client):
    response = client.get("/api/v1/communities")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert "message" in body["error"]


def test_login_sync_list_members_audit_flow(client):
    # unauthenticated -> 401
    assert client.get("/api/v1/session").status_code == 401

    # login
    login_response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "changeme123"}
    )
    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["username"] == "admin"
    assert login_body["role"] == "owner"
    assert "communeer_session" in client.cookies

    # bad credentials -> 401, envelope shape, no cookie change
    bad_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad_login.status_code == 401
    assert bad_login.json()["error"]["code"] == "unauthorized"

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


def test_advanced_query_param_includes_raw_metadata(client):
    client.post("/api/v1/auth/login", json={"username": "admin", "password": "changeme123"})
    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")

    plain = client.get(f"/api/v1/communities/{unity_alpha['id']}")
    assert "rawMetadata" not in plain.json()

    advanced = client.get(f"/api/v1/communities/{unity_alpha['id']}", params={"advanced": "true"})
    assert "rawMetadata" in advanced.json()
    assert "isParentGroup" in advanced.json()["rawMetadata"]
