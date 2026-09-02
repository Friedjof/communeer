"""`GET /api/v1/groups/{group_id}/messages` — the message-log endpoint (see
`communeer/groups/service.py::list_group_messages`).

Uses the shared session-scoped `app`/`client` fixtures (see conftest.py):
its DB is already primed with the mock provider's communities/groups/members
at app-lifespan startup. `GroupMessage` rows are inserted directly via the
ORM (the same "insert fixture state directly" pattern `test_moderation.py`
uses) rather than through the webhook — this file is about the read
endpoint's pagination/filtering, not ingestion (see `test_webhooks.py` for
that).
"""

import uuid as uuid_module
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from tests.conftest import login_as_admin as _login

TEST_SECRET = "test-webhook-secret"


def _unity_general_group_and_members(client) -> tuple[dict, list[dict]]:
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity = next(c for c in communities if c["name"] == "Unity Alpha")
    groups = client.get(f"/api/v1/communities/{unity['id']}/groups").json()
    general = next(g for g in groups if g["name"] == "General")
    members = client.get(f"/api/v1/groups/{general['id']}/members").json()
    assert len(members) >= 2, "test needs at least two distinct members"
    return general, members


def _insert_messages(group_id: str, member_id: str, entries: list[tuple[str, float]]) -> None:
    """`entries` is a list of `(content, minutes_ago)` pairs, inserted oldest
    call first but each with its own explicit `sent_at` so ordering in
    assertions is unambiguous regardless of insert order."""
    from communeer.db import SessionLocal
    from communeer.models import GroupMessage, MessageType

    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        for content, minutes_ago in entries:
            db.add(
                GroupMessage(
                    group_id=uuid_module.UUID(group_id),
                    member_id=uuid_module.UUID(member_id),
                    wa_message_id=f"test-log-{uuid_module.uuid4().hex}",
                    message_type=MessageType.text,
                    content=content,
                    sent_at=now - timedelta(minutes=minutes_ago),
                )
            )
        db.commit()
    finally:
        db.close()


def test_list_group_messages_orders_newest_first(client):
    group, members = _unity_general_group_and_members(client)
    member = members[0]
    # Well past `MESSAGE_BURST_WINDOW` (10 min) — this file shares the
    # session-scoped DB with `test_moderation.py`'s live end-to-end test, and
    # a cluster of messages inside that live window would trip its
    # `message_bursts` signal (a real, order-dependent interaction, not a bug
    # in either file).
    _insert_messages(group["id"], member["memberId"], [("oldest", 90), ("middle", 60), ("newest", 30)])

    response = client.get(f"/api/v1/groups/{group['id']}/messages")
    assert response.status_code == 200
    contents = [row["content"] for row in response.json() if row["content"] in ("oldest", "middle", "newest")]
    assert contents == ["newest", "middle", "oldest"]


def test_list_group_messages_pagination_via_before_cursor(client):
    group, members = _unity_general_group_and_members(client)
    member = members[0]
    # Offset well past `MESSAGE_BURST_WINDOW` (see comment above) — same
    # relative newest-first ordering, just shifted so this cluster doesn't
    # leak into `test_moderation.py`'s live-window assertions.
    _insert_messages(
        group["id"],
        member["memberId"],
        [(f"page-msg-{i}", 100 + i) for i in range(5)],
    )

    first_page = client.get(f"/api/v1/groups/{group['id']}/messages", params={"limit": 2, "search": "page-msg"})
    assert first_page.status_code == 200
    first_rows = first_page.json()
    assert [r["content"] for r in first_rows] == ["page-msg-0", "page-msg-1"]

    second_page = client.get(
        f"/api/v1/groups/{group['id']}/messages",
        params={"limit": 2, "search": "page-msg", "before": first_rows[-1]["sentAt"]},
    )
    assert second_page.status_code == 200
    second_rows = second_page.json()
    assert [r["content"] for r in second_rows] == ["page-msg-2", "page-msg-3"]
    # No overlap between pages.
    assert {r["id"] for r in first_rows}.isdisjoint({r["id"] for r in second_rows})


def test_list_group_messages_search_filters_by_content(client):
    group, members = _unity_general_group_and_members(client)
    member = members[0]
    _insert_messages(group["id"], member["memberId"], [("hello world", 101), ("goodbye moon", 102)])

    response = client.get(f"/api/v1/groups/{group['id']}/messages", params={"search": "world"})
    assert response.status_code == 200
    rows = response.json()
    assert any(r["content"] == "hello world" for r in rows)
    assert all("goodbye moon" != r["content"] for r in rows)


def test_list_group_messages_filters_by_member_id(client):
    group, members = _unity_general_group_and_members(client)
    member_a, member_b = members[0], members[1]
    _insert_messages(group["id"], member_a["memberId"], [("from A", 101)])
    _insert_messages(group["id"], member_b["memberId"], [("from B", 101)])

    response = client.get(f"/api/v1/groups/{group['id']}/messages", params={"member_id": member_a["memberId"]})
    assert response.status_code == 200
    rows = response.json()
    assert any(r["content"] == "from A" for r in rows)
    assert all(r["content"] != "from B" for r in rows)
    assert all(r["memberId"] == member_a["memberId"] for r in rows)


def test_list_group_messages_empty_group_returns_empty_list(client):
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity = next(c for c in communities if c["name"] == "Unity Alpha")
    groups = client.get(f"/api/v1/communities/{unity['id']}/groups").json()
    empty_ish = groups[-1]

    response = client.get(f"/api/v1/groups/{empty_ish['id']}/messages", params={"search": "no-such-content-xyz"})
    assert response.status_code == 200
    assert response.json() == []


def test_list_group_messages_unknown_group_returns_404(client):
    _login(client)
    response = client.get(f"/api/v1/groups/{uuid_module.uuid4()}/messages")
    assert response.status_code == 404


def _seed_viewer_user() -> None:
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


def test_list_group_messages_viewer_can_read(client):
    """A viewer has no `_require_manager` gate on this route (same read
    access as `list_group_members`/`list_group_requests`) — just no way to
    act on anything from it."""
    group, _members = _unity_general_group_and_members(client)
    _seed_viewer_user()

    login = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-123"})
    assert login.status_code == 200

    response = client.get(f"/api/v1/groups/{group['id']}/messages")
    assert response.status_code == 200
