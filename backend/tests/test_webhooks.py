"""`POST /api/v1/webhooks/wppconnect/{secret}` — the inbound WPPConnect
webhook receiver (see `communeer/webhooks/router.py`).

Uses the shared session-scoped `app`/`client` fixtures (see conftest.py):
its DB is already primed with the mock provider's communities/groups/
members at app-lifespan startup, so real group/member rows can be looked up
via the ordinary read endpoints rather than hand-constructing fixture data.
"""

from datetime import UTC, datetime, timedelta

TEST_SECRET = "test-webhook-secret"  # set in conftest.py's WEBHOOK_SECRET env var


def _login(client) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "changeme123"})
    assert response.status_code == 200


def _unity_general_group_and_members(client) -> tuple[dict, list[dict]]:
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity = next(c for c in communities if c["name"] == "Unity Alpha")
    groups = client.get(f"/api/v1/communities/{unity['id']}/groups").json()
    general = next(g for g in groups if g["name"] == "General")
    members = client.get(f"/api/v1/groups/{general['id']}/members").json()
    assert len(members) >= 2, "test needs at least two distinct members to avoid cross-test interference"
    return general, members


def test_webhook_wrong_secret_returns_404(client):
    response = client.post(
        "/api/v1/webhooks/wppconnect/definitely-not-the-secret",
        json={"event": "onmessage", "type": "chat"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_webhook_onmessage_updates_activity_forward_only_and_last_message_at(client):
    group, members = _unity_general_group_and_members(client)
    group_wa_id = group["waId"]
    member = members[0]
    member_wa_id = member["waId"]

    older_t = int((datetime.now(UTC) - timedelta(days=2)).timestamp())
    payload = {
        "event": "onmessage",
        "session": "communeer",
        "type": "chat",
        "fromMe": False,
        "chatId": group_wa_id,
        "author": member_wa_id,
        "t": older_t,
        "body": 'Hello from the webhook test, with a comma, and "quotes" too',
    }
    response = client.post(f"/api/v1/webhooks/wppconnect/{TEST_SECRET}", json=payload)
    assert response.status_code == 200

    updated_members = client.get(f"/api/v1/groups/{group['id']}/members").json()
    updated = next(m for m in updated_members if m["waId"] == member_wa_id)
    assert updated["lastActivityType"] == "message"
    assert updated["lastActivityContent"] == payload["body"]
    assert updated["lastActivityAt"] is not None
    assert updated["lastMessageAt"] is not None
    first_activity_at = updated["lastActivityAt"]

    # A later webhook call reporting an EARLIER timestamp must not regress
    # the already-stamped value (forward-only, same discipline as
    # `sync_community`'s own `last_message_at` stamping).
    even_older_t = int((datetime.now(UTC) - timedelta(days=10)).timestamp())
    stale_payload = dict(payload, t=even_older_t, body="a stale, older message")
    response2 = client.post(f"/api/v1/webhooks/wppconnect/{TEST_SECRET}", json=stale_payload)
    assert response2.status_code == 200

    unchanged_members = client.get(f"/api/v1/groups/{group['id']}/members").json()
    unchanged = next(m for m in unchanged_members if m["waId"] == member_wa_id)
    assert unchanged["lastActivityAt"] == first_activity_at
    assert unchanged["lastActivityContent"] == payload["body"]

    # A later webhook call reporting a genuinely NEWER timestamp must
    # advance both fields forward.
    newer_t = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())
    newer_payload = dict(payload, t=newer_t, body="a fresh, newer message")
    response3 = client.post(f"/api/v1/webhooks/wppconnect/{TEST_SECRET}", json=newer_payload)
    assert response3.status_code == 200

    advanced_members = client.get(f"/api/v1/groups/{group['id']}/members").json()
    advanced = next(m for m in advanced_members if m["waId"] == member_wa_id)
    assert advanced["lastActivityAt"] != first_activity_at
    assert advanced["lastActivityContent"] == "a fresh, newer message"


def test_webhook_onreactionmessage_updates_activity_but_not_last_message_at(client):
    group, members = _unity_general_group_and_members(client)
    group_wa_id = group["waId"]
    # A different member than the onmessage test above, so the two tests
    # (which share the same session-scoped DB) can't clobber each other's
    # assertions regardless of execution order.
    member = members[1]
    member_wa_id = member["waId"]
    before_last_message_at = member["lastMessageAt"]

    reaction_t = int((datetime.now(UTC) - timedelta(hours=3)).timestamp())
    payload = {
        "event": "onreactionmessage",
        "session": "communeer",
        "id": {"fromMe": False, "remote": group_wa_id, "id": "reaction-key-1", "participant": None},
        "msgId": {"fromMe": False, "remote": group_wa_id, "id": "original-message-key-1", "participant": None},
        "reactionText": "👍",
        "read": False,
        "sender": member_wa_id,
        "orphan": 0,
        "orphanReason": None,
        "timestamp": reaction_t,
    }
    response = client.post(f"/api/v1/webhooks/wppconnect/{TEST_SECRET}", json=payload)
    assert response.status_code == 200

    updated_members = client.get(f"/api/v1/groups/{group['id']}/members").json()
    updated = next(m for m in updated_members if m["waId"] == member_wa_id)
    assert updated["lastActivityType"] == "reaction"
    assert updated["lastActivityContent"] == "👍"
    assert updated["lastActivityAt"] is not None
    # A reaction is a weaker signal than an actual message — must never
    # touch `last_message_at` (the field `get_renewal_suggestions` sorts on).
    assert updated["lastMessageAt"] == before_last_message_at
    first_activity_at = updated["lastActivityAt"]

    # Forward-only applies to reactions too: an earlier reaction timestamp
    # must not regress the stamped value.
    earlier_t = int((datetime.now(UTC) - timedelta(days=5)).timestamp())
    stale_payload = dict(payload, timestamp=earlier_t, reactionText="😀")
    response2 = client.post(f"/api/v1/webhooks/wppconnect/{TEST_SECRET}", json=stale_payload)
    assert response2.status_code == 200

    unchanged_members = client.get(f"/api/v1/groups/{group['id']}/members").json()
    unchanged = next(m for m in unchanged_members if m["waId"] == member_wa_id)
    assert unchanged["lastActivityAt"] == first_activity_at
    assert unchanged["lastActivityContent"] == "👍"
    assert unchanged["lastMessageAt"] == before_last_message_at


def test_webhook_unrecognized_event_is_a_no_op_200(client):
    response = client.post(
        f"/api/v1/webhooks/wppconnect/{TEST_SECRET}",
        json={"event": "something-unknown", "foo": "bar"},
    )
    assert response.status_code == 200


def _audit_sync_event_count(client, community_id: str) -> int:
    audit = client.get("/api/v1/audit", params={"action": "community.sync"}).json()
    return len([row for row in audit if row["targetId"] == community_id])


def test_webhook_onparticipantschanged_with_known_group_triggers_resync(client):
    """A valid group id must trigger a real resync of its community (see
    `_handle_onparticipantschanged` -> `sync_community`) — asserted here via
    the audit trail, since the mock provider's fixture data is deterministic
    (a plain resync is otherwise indistinguishable from a no-op)."""
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity = next(c for c in communities if c["name"] == "Unity Alpha")
    groups = client.get(f"/api/v1/communities/{unity['id']}/groups").json()
    general = next(g for g in groups if g["name"] == "General")

    sync_events_before = _audit_sync_event_count(client, unity["id"])

    response = client.post(
        f"/api/v1/webhooks/wppconnect/{TEST_SECRET}",
        json={
            "event": "onparticipantschanged",
            "session": "communeer",
            "chatId": general["waId"],
            "action": "add",
        },
    )
    assert response.status_code == 200

    sync_events_after = _audit_sync_event_count(client, unity["id"])
    assert sync_events_after == sync_events_before + 1


def test_webhook_onparticipantschanged_with_unknown_group_is_a_safe_no_op(client):
    """A group id this instance has never synced (or a payload with no
    usable id field at all) must be a safe no-op — not a 404/500, and
    critically must not raise `AttributeError` trying to reach `.community`
    off a `None` group."""
    _login(client)

    response = client.post(
        f"/api/v1/webhooks/wppconnect/{TEST_SECRET}",
        json={
            "event": "onparticipantschanged",
            "session": "communeer",
            "chatId": "000000000000000000@g.us",
            "action": "add",
        },
    )
    assert response.status_code == 200

    response_no_id = client.post(
        f"/api/v1/webhooks/wppconnect/{TEST_SECRET}",
        json={"event": "onparticipantschanged", "session": "communeer", "action": "add"},
    )
    assert response_no_id.status_code == 200


def test_webhook_onparticipantschanged_logs_and_returns_200_when_provider_unavailable(client, monkeypatch):
    """A WPPConnect transport failure during the webhook-triggered resync
    (translated to `WhatsAppProviderUnavailableError`, see
    `providers/whatsapp/wppconnect.py`) must not crash this fire-and-forget
    server-to-server request with a 500 — `_handle_onparticipantschanged`
    catches it and logs a warning instead (see `webhooks/router.py`).

    Asserted by monkeypatching the module's `logger.warning` directly
    rather than via `caplog`: this app's `_run_migrations()` re-invokes
    Alembic's `Config` on every lifespan startup (i.e. on every test's fresh
    `TestClient`), and Alembic's `alembic.ini` drives `fileConfig()` with its
    historical `disable_existing_loggers=True` default — which silently
    disables every `communeer.*` logger not explicitly listed in that ini
    (an existing, out-of-scope quirk of this app's logging setup, not
    something this task's plan covers), making `caplog` unreliable here.
    """
    import communeer.webhooks.router as webhooks_router_module
    from communeer.providers.whatsapp.base import WhatsAppProviderUnavailableError

    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity = next(c for c in communities if c["name"] == "Unity Alpha")
    groups = client.get(f"/api/v1/communities/{unity['id']}/groups").json()
    general = next(g for g in groups if g["name"] == "General")

    def _raise_unavailable(*args, **kwargs):
        raise WhatsAppProviderUnavailableError("boom")

    monkeypatch.setattr(webhooks_router_module, "sync_community", _raise_unavailable)

    warning_calls: list[str] = []
    monkeypatch.setattr(webhooks_router_module.logger, "warning", lambda msg, *args: warning_calls.append(msg))

    response = client.post(
        f"/api/v1/webhooks/wppconnect/{TEST_SECRET}",
        json={"event": "onparticipantschanged", "session": "communeer", "chatId": general["waId"], "action": "add"},
    )

    assert response.status_code == 200
    assert any("provider unavailable" in msg for msg in warning_calls)
