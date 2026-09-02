"""Tests for the audit log's filter query params (`action`, `targetType`,
`since`, `until`) — added on top of the existing flat, unfiltered list.
"""

from datetime import UTC, datetime, timedelta

from tests.conftest import login_as_admin as _login


def test_filter_by_action_returns_only_matching_events(client):
    _login(client)
    # a failed login (auth.login_failed) alongside the already-recorded auth.login
    client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})

    response = client.get("/api/v1/audit", params={"action": "auth.login_failed"})
    assert response.status_code == 200
    actions = {row["action"] for row in response.json()}
    assert actions == {"auth.login_failed"}


def test_filter_by_target_type_returns_only_matching_events(client):
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")
    client.post(f"/api/v1/communities/{unity_alpha['id']}/sync")

    response = client.get("/api/v1/audit", params={"targetType": "community"})
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    assert all(row["targetType"] == "community" for row in events)
    # auth.login has target_type "user", so filtering must actually exclude it
    assert all(row["action"] != "auth.login" for row in events)


def test_filter_by_date_range_excludes_events_outside_window(client):
    _login(client)

    far_future_since = (datetime.now(UTC) + timedelta(days=365)).isoformat()
    response = client.get("/api/v1/audit", params={"since": far_future_since})
    assert response.status_code == 200
    assert response.json() == []

    far_past_until = (datetime.now(UTC) - timedelta(days=365)).isoformat()
    response = client.get("/api/v1/audit", params={"until": far_past_until})
    assert response.status_code == 200
    assert response.json() == []

    # a wide-enough window still returns the just-recorded login
    wide_since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    response = client.get("/api/v1/audit", params={"since": wide_since})
    assert response.status_code == 200
    assert any(row["action"] == "auth.login" for row in response.json())
