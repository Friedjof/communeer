"""Unit tests for `WppconnectProvider`, mocking the WPPConnect Server's HTTP
API with `respx` shaped per the plan's documented (unverified-against-real-
data) hypothesis: `list-chats` embeds `groupMetadata.isParentGroup` /
`parentGroup` / `announce`. These tests only prove the parsing/derivation
logic is correct *given* that shape — they do not (and cannot) prove the
hypothesis itself holds against a real WPPConnect Server.
"""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from communeer.config import Settings
from communeer.providers.whatsapp import wppconnect as wppconnect_module
from communeer.providers.whatsapp.base import (
    WhatsAppNotConnectedError,
    WhatsAppProviderUnavailableError,
)
from communeer.providers.whatsapp.wppconnect import WppconnectProvider


@pytest.fixture(autouse=True)
def _no_retry_backoff_delay(monkeypatch):
    """`_request_with_retry`'s backoff sleeps real seconds between attempts
    — every test in this file hitting a transient-error path (retried or
    not) would otherwise actually wait for it. Patched to a no-op here so
    only the retry *behavior* is under test, never wall-clock time."""
    monkeypatch.setattr(wppconnect_module.time, "sleep", lambda _seconds: None)

BASE_URL = "http://wppconnect-test:21465"
SESSION = "testsession"
SECRET_KEY = "secretkey"

ROOT_WA_ID = "120363000000000001@g.us"
ANNOUNCEMENTS_WA_ID = "120363000000000010@g.us"
GENERAL_WA_ID = "120363000000000011@g.us"
PENDING_MEMBER_JID = "4915512345678@c.us"
MEMBER_JID = "4915598765432@c.us"


def _settings() -> Settings:
    return Settings(
        wppconnect_base_url=BASE_URL,
        wppconnect_secret_key=SECRET_KEY,
        wppconnect_session_name=SESSION,
        wppconnect_http_timeout_seconds=5.0,
    )


def _provider() -> WppconnectProvider:
    return WppconnectProvider(_settings())


def _generate_token_url() -> str:
    return f"{BASE_URL}/api/{SESSION}/{SECRET_KEY}/generate-token"


def _status_session_url() -> str:
    return f"{BASE_URL}/api/{SESSION}/status-session"


def _list_chats_url() -> str:
    return f"{BASE_URL}/api/{SESSION}/list-chats"


def _group_members_url(wa_id: str) -> str:
    return f"{BASE_URL}/api/{SESSION}/group-members/{wa_id}"


def _group_admins_url(wa_id: str) -> str:
    return f"{BASE_URL}/api/{SESSION}/group-admins/{wa_id}"


def _get_messages_url(wa_id: str) -> str:
    return f"{BASE_URL}/api/{SESSION}/get-messages/{wa_id}"


def _start_session_url() -> str:
    return f"{BASE_URL}/api/{SESSION}/start-session"


def _mock_token_and_connected(respx_mock) -> None:
    respx_mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx_mock.get(_status_session_url()).respond(200, json={"status": "CONNECTED"})


def _jid(wa_id: str) -> dict:
    """Real WPPConnect `id`/`parentGroup` fields are `{"server", "user",
    "_serialized"}` objects, not plain strings — confirmed against a real
    account (see wppconnect.py's `_jid_str` docstring). A prior version of
    this fixture used a bare string for `parentGroup`, which happened to
    match `WppconnectProvider`'s (then-buggy) `== root_wa_id` comparison and
    masked the fact that real data never would."""
    user, _, server = wa_id.partition("@")
    return {"server": server, "user": user, "_serialized": wa_id}


def _happy_path_chats() -> list[dict]:
    return [
        {
            "groupMetadata": {
                "id": _jid(ROOT_WA_ID),
                "subject": "Test Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
                "desc": "Root community group",
            }
        },
        {
            "groupMetadata": {
                "id": _jid(ANNOUNCEMENTS_WA_ID),
                "subject": "Announcements",
                "isParentGroup": False,
                "parentGroup": _jid(ROOT_WA_ID),
                "announce": True,
                "size": 2,
                "pendingParticipants": [],
            }
        },
        {
            "groupMetadata": {
                "id": _jid(GENERAL_WA_ID),
                "subject": "General",
                "isParentGroup": False,
                "parentGroup": _jid(ROOT_WA_ID),
                "announce": False,
                "size": 2,
                "pendingParticipants": [{"id": {"_serialized": PENDING_MEMBER_JID}}],
            }
        },
    ]


@respx.mock
def test_get_communities_happy_path_builds_expected_tree():
    _mock_token_and_connected(respx.mock)
    respx.mock.post(_list_chats_url()).respond(200, json=_happy_path_chats())

    respx.mock.get(_group_members_url(ANNOUNCEMENTS_WA_ID)).respond(
        200, json=[{"id": {"_serialized": MEMBER_JID}, "pushname": "Alice"}]
    )
    # `group-admins` was confirmed against a real account to return the Wid
    # object directly (no `.id` wrapper) nested one list-level deeper than
    # `group-members` — `{"status": "success", "response": [[...]]}` even
    # for a single group.
    respx.mock.get(_group_admins_url(ANNOUNCEMENTS_WA_ID)).respond(
        200, json={"status": "success", "response": [[_jid(MEMBER_JID)]]}
    )
    respx.mock.get(_group_members_url(GENERAL_WA_ID)).respond(
        200,
        json=[
            {"id": {"_serialized": MEMBER_JID}, "pushname": "Alice"},
            {"id": {"_serialized": PENDING_MEMBER_JID}},
        ],
    )
    respx.mock.get(_group_admins_url(GENERAL_WA_ID)).respond(200, json=[])
    respx.mock.get(_get_messages_url(ANNOUNCEMENTS_WA_ID)).respond(
        200, json={"status": "success", "response": []}
    )
    respx.mock.get(_get_messages_url(GENERAL_WA_ID)).respond(
        200, json={"status": "success", "response": []}
    )

    provider = _provider()
    communities = provider.get_communities()

    assert len(communities) == 1
    community = communities[0]
    assert community.wa_id == ROOT_WA_ID
    assert community.name == "Test Community"
    assert community.announcement_group_wa_id == ANNOUNCEMENTS_WA_ID
    assert {g.wa_id for g in community.groups} == {ANNOUNCEMENTS_WA_ID, GENERAL_WA_ID}

    announcements = next(g for g in community.groups if g.wa_id == ANNOUNCEMENTS_WA_ID)
    assert announcements.is_announcement_group is True
    # `size` is the group's *current* member count, not a configured limit —
    # WPPConnect exposes no real cap field. The limit comes from WhatsApp's
    # own documented platform caps instead: the announcement group shares
    # the community-wide cap (2000), a regular subgroup is capped at 1024.
    assert announcements.member_limit == 2000
    general = next(g for g in community.groups if g.wa_id == GENERAL_WA_ID)
    assert general.member_limit == 1024
    assert len(announcements.memberships) == 1
    assert announcements.memberships[0].is_admin is True
    assert announcements.memberships[0].member.wa_id == MEMBER_JID
    assert announcements.memberships[0].member.display_name == "Alice"

    general = next(g for g in community.groups if g.wa_id == GENERAL_WA_ID)
    assert general.is_announcement_group is False
    memberships_by_wa_id = {m.member.wa_id: m for m in general.memberships}
    assert memberships_by_wa_id[PENDING_MEMBER_JID].status == "pending"
    assert memberships_by_wa_id[MEMBER_JID].status == "member"
    assert memberships_by_wa_id[MEMBER_JID].is_admin is False
    # phone masking applied even without a pushname
    assert memberships_by_wa_id[PENDING_MEMBER_JID].member.display_name.startswith("+")


@respx.mock
def test_get_messages_filters_non_chat_types_and_aggregates_last_message_at_per_author():
    """`get-messages` is fetched once per group; only `type == "chat"` rows
    are real user-written messages — others (e.g. `"gp2"`, a system/
    notification event like a join) must be excluded. `last_message_at` per
    author is the max `t` among their `"chat"` messages only, converted to a
    timezone-aware UTC `datetime`. Mirrors the real shape confirmed live:
    `author` is a plain string JID (not the `{"id": ...}` wrapper
    `group-members`/`group-admins` use)."""
    _mock_token_and_connected(respx.mock)

    author_a = "124193425358871@lid"
    author_b = "133139942899781@lid"

    chats = [
        {
            "groupMetadata": {
                "id": _jid(ROOT_WA_ID),
                "subject": "Test Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(GENERAL_WA_ID),
                "subject": "General",
                "isParentGroup": False,
                "parentGroup": _jid(ROOT_WA_ID),
                "announce": False,
            }
        },
    ]
    respx.mock.post(_list_chats_url()).respond(200, json=chats)
    respx.mock.get(_group_members_url(GENERAL_WA_ID)).respond(
        200,
        json=[
            {"id": {"_serialized": author_a}, "pushname": "Alice"},
            {"id": {"_serialized": author_b}, "pushname": "Bob"},
        ],
    )
    respx.mock.get(_group_admins_url(GENERAL_WA_ID)).respond(200, json=[])
    respx.mock.get(_get_messages_url(GENERAL_WA_ID)).respond(
        200,
        json={
            "status": "success",
            "response": [
                {"id": "1", "type": "chat", "t": 1787587079, "author": author_a, "body": "Hii I'm looking for..."},
                # a later timestamp, but not a real chat message — must be excluded.
                {"id": "2", "type": "gp2", "t": 1787999999, "author": author_a, "body": "joined the group"},
                {"id": "3", "type": "chat", "t": 1787500000, "author": author_a, "body": "an earlier message"},
                {"id": "4", "type": "chat", "t": 1787633724, "author": author_b, "body": "+1"},
            ],
        },
    )

    provider = _provider()
    group = provider.get_group(GENERAL_WA_ID)

    memberships_by_author = {m.member.wa_id: m for m in group.memberships}

    assert memberships_by_author[author_a].last_message_at == datetime.fromtimestamp(1787587079, tz=UTC)
    assert memberships_by_author[author_b].last_message_at == datetime.fromtimestamp(1787633724, tz=UTC)
    # `last_seen_at` is never populated by this provider (see wppconnect.py).
    assert memberships_by_author[author_a].last_seen_at is None
    assert memberships_by_author[author_b].last_seen_at is None

    # Real chat history must also feed the unified `last_activity_*` fields
    # (previously these were only ever set by the live webhook, so existing
    # history was invisible to them — this is exactly that gap, fixed).
    assert memberships_by_author[author_a].last_activity_type == "message"
    assert memberships_by_author[author_a].last_activity_at == datetime.fromtimestamp(1787587079, tz=UTC)
    assert memberships_by_author[author_a].last_activity_content == "Hii I'm looking for..."
    assert memberships_by_author[author_b].last_activity_type == "message"
    assert memberships_by_author[author_b].last_activity_content == "+1"


@respx.mock
def test_get_messages_truncates_long_body_for_last_activity_content():
    """A message body longer than 200 characters must be truncated for
    `last_activity_content` — matches `webhooks/router.py`'s
    `_ACTIVITY_CONTENT_MAX_LEN`, same field, same limit."""
    _mock_token_and_connected(respx.mock)

    author = "124193425358871@lid"
    long_body = "x" * 250

    chats = [
        {
            "groupMetadata": {
                "id": _jid(ROOT_WA_ID),
                "subject": "Test Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(GENERAL_WA_ID),
                "subject": "General",
                "isParentGroup": False,
                "parentGroup": _jid(ROOT_WA_ID),
                "announce": False,
            }
        },
    ]
    respx.mock.post(_list_chats_url()).respond(200, json=chats)
    respx.mock.get(_group_members_url(GENERAL_WA_ID)).respond(
        200, json=[{"id": {"_serialized": author}, "pushname": "Alice"}]
    )
    respx.mock.get(_group_admins_url(GENERAL_WA_ID)).respond(200, json=[])
    respx.mock.get(_get_messages_url(GENERAL_WA_ID)).respond(
        200,
        json={"status": "success", "response": [{"id": "1", "type": "chat", "t": 1787587079, "author": author, "body": long_body}]},
    )

    provider = _provider()
    group = provider.get_group(GENERAL_WA_ID)

    membership = next(m for m in group.memberships if m.member.wa_id == author)
    assert membership.last_activity_content == "x" * 200
    assert len(membership.last_activity_content) == 200


@respx.mock
def test_get_messages_author_with_no_chat_messages_gets_none_not_zero():
    """An author present in the roster but absent from the fetched
    `get-messages` window (or only present via non-`"chat"` rows) must get
    `last_message_at=None` — never `0`/epoch, never an exception."""
    _mock_token_and_connected(respx.mock)

    silent_author = "111111111111111@lid"

    chats = [
        {
            "groupMetadata": {
                "id": _jid(ROOT_WA_ID),
                "subject": "Test Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(GENERAL_WA_ID),
                "subject": "General",
                "isParentGroup": False,
                "parentGroup": _jid(ROOT_WA_ID),
                "announce": False,
            }
        },
    ]
    respx.mock.post(_list_chats_url()).respond(200, json=chats)
    respx.mock.get(_group_members_url(GENERAL_WA_ID)).respond(
        200, json=[{"id": {"_serialized": silent_author}, "pushname": "Silent"}]
    )
    respx.mock.get(_group_admins_url(GENERAL_WA_ID)).respond(200, json=[])
    respx.mock.get(_get_messages_url(GENERAL_WA_ID)).respond(
        200,
        json={
            "status": "success",
            "response": [
                {"id": "1", "type": "gp2", "t": 1787999999, "author": silent_author, "body": "joined"},
            ],
        },
    )

    provider = _provider()
    group = provider.get_group(GENERAL_WA_ID)

    membership = next(m for m in group.memberships if m.member.wa_id == silent_author)
    assert membership.last_message_at is None
    assert membership.last_activity_type is None
    assert membership.last_activity_at is None
    assert membership.last_activity_content is None


@respx.mock
def test_get_communities_raises_when_no_structure_fields_present():
    _mock_token_and_connected(respx.mock)
    # Non-empty group list, but nothing carries isParentGroup/parentGroup —
    # the hypothesis-violation tripwire.
    respx.mock.post(_list_chats_url()).respond(
        200,
        json=[
            {"groupMetadata": {"id": {"_serialized": "1@g.us"}, "subject": "Just A Group"}},
            {"groupMetadata": {"id": {"_serialized": "2@g.us"}, "subject": "Another Group"}},
        ],
    )

    provider = _provider()
    with pytest.raises(RuntimeError, match="isParentGroup/parentGroup"):
        provider.get_communities()


@respx.mock
def test_get_communities_raises_not_connected_when_session_closed():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_status_session_url()).respond(200, json={"status": "CLOSED"})

    provider = _provider()
    with pytest.raises(WhatsAppNotConnectedError):
        provider.get_communities()


@respx.mock
def test_get_group_raises_not_connected_when_session_closed():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_status_session_url()).respond(200, json={"status": "QRCODE", "qrcode": "data:image/png;base64,x"})

    provider = _provider()
    with pytest.raises(WhatsAppNotConnectedError):
        provider.get_group(GENERAL_WA_ID)


@respx.mock
def test_authed_request_retries_once_after_401():
    token_route = respx.mock.post(_generate_token_url())
    token_route.side_effect = [
        httpx.Response(200, json={"token": "expired-token"}),
        httpx.Response(200, json={"token": "fresh-token"}),
    ]

    target_route = respx.mock.get(_status_session_url())
    target_route.side_effect = [
        httpx.Response(401, json={"error": "expired"}),
        httpx.Response(200, json={"status": "CONNECTED"}),
    ]

    provider = _provider()
    resp = provider._authed_request("GET", f"/api/{SESSION}/status-session")

    assert resp.status_code == 200
    assert resp.json()["status"] == "CONNECTED"
    assert token_route.call_count == 2
    assert target_route.call_count == 2
    assert provider._token == "fresh-token"


@respx.mock
def test_get_admin_community_wa_ids_filters_by_isme_flag_in_group_admins():
    """Mirrors what was actually confirmed against a live session (see
    `wppconnect.py`'s module docstring): the connected account's own id, as
    used by `group-admins`, is whatever `group-members` flags `isMe: true`
    on — in the `@lid` namespace, distinct from any `@c.us` phone id. This
    fixture models two communities: one where that `isMe`-flagged id is a
    `group-admins` admin (should be included), one where it isn't (should
    be excluded)."""
    _mock_token_and_connected(respx.mock)

    admin_root_wa_id = "120363100000000001@g.us"
    admin_announce_wa_id = "120363100000000010@g.us"
    other_root_wa_id = "120363200000000001@g.us"
    other_announce_wa_id = "120363200000000010@g.us"

    own_lid = "111111111111111@lid"
    other_admin_lid = "999999999999999@lid"

    chats = [
        {
            "groupMetadata": {
                "id": _jid(admin_root_wa_id),
                "subject": "Admin Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(admin_announce_wa_id),
                "subject": "Announcements",
                "isParentGroup": False,
                "parentGroup": _jid(admin_root_wa_id),
                "announce": True,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(other_root_wa_id),
                "subject": "Other Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(other_announce_wa_id),
                "subject": "Announcements",
                "isParentGroup": False,
                "parentGroup": _jid(other_root_wa_id),
                "announce": True,
            }
        },
    ]
    respx.mock.post(_list_chats_url()).respond(200, json=chats)

    # `_find_own_wa_id` tries groups in `list-chats` order and stops at the
    # first `group-members` response containing an `isMe: true` entry — the
    # first chat is the admin community's root group itself.
    respx.mock.get(_group_members_url(admin_root_wa_id)).respond(
        200,
        json=[
            {"id": {"_serialized": own_lid}, "isMe": True, "pushname": "Du"},
        ],
    )
    respx.mock.get(_group_admins_url(admin_announce_wa_id)).respond(
        200, json={"status": "success", "response": [[_jid(own_lid)]]}
    )
    respx.mock.get(_group_admins_url(other_announce_wa_id)).respond(
        200, json={"status": "success", "response": [[_jid(other_admin_lid)]]}
    )

    provider = _provider()

    assert provider.get_own_wa_id() == own_lid
    assert provider.get_admin_community_wa_ids() == {admin_root_wa_id}


@respx.mock
def test_get_admin_community_wa_ids_returns_none_when_own_id_cannot_be_found():
    """No `group-members` response ever carries `isMe: true` — e.g. the
    account isn't (yet) a member of any visible group. Must degrade to
    `None` ("can't determine, don't filter"), not an empty set."""
    _mock_token_and_connected(respx.mock)

    root_wa_id = "120363300000000001@g.us"
    announce_wa_id = "120363300000000010@g.us"
    chats = [
        {
            "groupMetadata": {
                "id": _jid(root_wa_id),
                "subject": "Some Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(announce_wa_id),
                "subject": "Announcements",
                "isParentGroup": False,
                "parentGroup": _jid(root_wa_id),
                "announce": True,
            }
        },
    ]
    respx.mock.post(_list_chats_url()).respond(200, json=chats)
    # `_find_own_wa_id` tries every visible group in turn until one
    # response's roster carries `isMe: true` — mock both groups here with
    # no such entry, so it correctly exhausts the search and returns `None`.
    respx.mock.get(_group_members_url(root_wa_id)).respond(
        200, json=[{"id": {"_serialized": "123@lid"}, "isMe": False}]
    )
    respx.mock.get(_group_members_url(announce_wa_id)).respond(
        200, json=[{"id": {"_serialized": "456@lid"}, "isMe": False}]
    )

    provider = _provider()

    assert provider.get_own_wa_id() is None
    assert provider.get_admin_community_wa_ids() is None


@respx.mock
def test_get_admin_community_wa_ids_includes_community_with_no_detected_announcement_group():
    """A community whose announcement group can't be matched (no `announce:
    True` chat pointing back to it via `parentGroup`) is "can't tell if the
    connected account administers it," not "confirmed not an admin" — same
    fail-open principle as the top-level `None` return, applied per
    community. Must be *included*, not silently dropped."""
    _mock_token_and_connected(respx.mock)

    root_wa_id = "120363400000000001@g.us"
    own_lid = "111111111111111@lid"

    chats = [
        {
            "groupMetadata": {
                "id": _jid(root_wa_id),
                "subject": "Orphan Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
    ]
    respx.mock.post(_list_chats_url()).respond(200, json=chats)
    respx.mock.get(_group_members_url(root_wa_id)).respond(
        200,
        json=[{"id": {"_serialized": own_lid}, "isMe": True, "pushname": "Du"}],
    )

    provider = _provider()

    assert provider.get_admin_community_wa_ids() == {root_wa_id}


@respx.mock
def test_get_admin_community_wa_ids_includes_community_when_group_admins_call_fails():
    """A transient `group-admins` failure for one community's announcement
    group must not exclude that community either — same fail-open principle
    as above, this time triggered by a transport error instead of a missing
    announcement group."""
    _mock_token_and_connected(respx.mock)

    root_wa_id = "120363500000000001@g.us"
    announce_wa_id = "120363500000000010@g.us"
    own_lid = "111111111111111@lid"

    chats = [
        {
            "groupMetadata": {
                "id": _jid(root_wa_id),
                "subject": "Flaky Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(announce_wa_id),
                "subject": "Announcements",
                "isParentGroup": False,
                "parentGroup": _jid(root_wa_id),
                "announce": True,
            }
        },
    ]
    respx.mock.post(_list_chats_url()).respond(200, json=chats)
    respx.mock.get(_group_members_url(root_wa_id)).respond(
        200,
        json=[{"id": {"_serialized": own_lid}, "isMe": True, "pushname": "Du"}],
    )
    respx.mock.get(_group_admins_url(announce_wa_id)).mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    provider = _provider()

    assert provider.get_admin_community_wa_ids() == {root_wa_id}


@respx.mock
def test_get_admin_community_wa_ids_returns_none_when_not_connected():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_status_session_url()).respond(200, json={"status": "CLOSED"})

    provider = _provider()

    assert provider.get_own_wa_id() is None
    assert provider.get_admin_community_wa_ids() is None


@respx.mock
def test_authed_request_retries_transient_timeout_and_succeeds():
    """A community with many groups fans out to many WPPConnect calls
    (`_build_memberships`) — one of them hitting a transient timeout used to
    take down the *entire* community's sync. Two timeouts followed by a real
    response must now succeed rather than propagate."""
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_status_session_url()).mock(
        side_effect=[
            httpx.TimeoutException("timed out"),
            httpx.TimeoutException("timed out"),
            httpx.Response(200, json={"status": "CONNECTED"}),
        ]
    )

    provider = _provider()
    status = provider.get_connection_status()

    assert status.state.value == "connected"


@respx.mock
def test_authed_request_gives_up_after_max_transient_retries():
    """More consecutive transient failures than the retry budget allows
    must still surface as a failure — retrying is a resilience improvement,
    not a way to hide a genuinely down WPPConnect server forever."""
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_status_session_url()).mock(side_effect=httpx.TimeoutException("timed out"))

    provider = _provider()
    status = provider.get_connection_status()

    assert status.state.value == "error"


@respx.mock
def test_authed_request_does_not_retry_a_real_http_error_status():
    """A real HTTP error response (as opposed to a transport-level
    exception) must not be retried — retrying is only for genuinely
    transient timeout/connect failures, never a server's actual answer."""
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    route = respx.mock.get(_status_session_url()).respond(500)

    provider = _provider()
    provider.get_connection_status()

    assert route.call_count == 1


@respx.mock
def test_get_connection_status_never_raises_on_transport_error():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_status_session_url()).mock(side_effect=httpx.ConnectError("connection refused"))

    provider = _provider()
    status = provider.get_connection_status()

    assert status.state.value == "error"
    assert status.detail is not None
    # `status-session` itself never embeds the secret (only `generate-token`'s
    # own URL does), so the exception's own type name is expected to appear;
    # what must never appear, on any failure path, is the secret itself (see
    # the dedicated leak test below) — asserting the exact raw exception text
    # would be the wrong thing to lock in now that `_safe_error_detail`
    # deliberately replaces it with a generic message.
    assert status.detail == "ConnectError: request to WhatsApp provider failed"
    assert SECRET_KEY not in status.detail


@respx.mock
def test_get_connection_status_does_not_leak_secret_key_on_generate_token_failure():
    """The actual bug this guards against: `_ensure_token()` embeds
    `self._secret_key` directly in the `generate-token` request URL
    (`/api/{session}/{secret_key}/generate-token`). `httpx.HTTPStatusError`
    (raised by `raise_for_status()`) embeds the full request URL in its own
    `str()` — so if `get_connection_status()` ever went back to using
    `str(exc)` verbatim, a failing `generate-token` call would leak
    `WPPCONNECT_SECRET_KEY` in plaintext into `detail`, which `GET
    /whatsapp/status` returns to every authenticated user, including
    `viewer`."""
    respx.mock.post(_generate_token_url()).respond(500, json={"error": "boom"})

    provider = _provider()
    status = provider.get_connection_status()

    assert status.state.value == "error"
    assert status.detail is not None
    assert SECRET_KEY not in status.detail
    assert _generate_token_url() not in status.detail
    assert status.detail == "HTTPStatusError: request to WhatsApp provider failed"


@respx.mock
def test_start_session_raises_provider_unavailable_on_transport_error():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.post(_start_session_url()).mock(side_effect=httpx.ConnectError("connection refused"))

    provider = _provider()

    with pytest.raises(WhatsAppProviderUnavailableError):
        provider.start_session()


@respx.mock
def test_start_session_succeeds_when_wppconnect_is_reachable():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.post(_start_session_url()).respond(200, json={"status": "success"})

    provider = _provider()

    provider.start_session()  # must not raise


# ---------------------------------------------------------------------------
# Consistent httpx-error translation: get_communities/get_community/get_group/
# get_members (and their internal _fetch_groups_raw/_build_memberships/
# _fetch_last_message_by_author helpers) must translate a transport failure
# into WhatsAppProviderUnavailableError, exactly like start_session() already
# does — instead of letting a raw httpx.HTTPError propagate to a generic 500.
# ---------------------------------------------------------------------------


@respx.mock
def test_get_communities_raises_provider_unavailable_on_list_chats_failure():
    _mock_token_and_connected(respx.mock)
    respx.mock.post(_list_chats_url()).mock(side_effect=httpx.ConnectError("connection refused"))

    provider = _provider()
    with pytest.raises(WhatsAppProviderUnavailableError):
        provider.get_communities()


@respx.mock
def test_get_group_raises_provider_unavailable_on_group_members_failure():
    _mock_token_and_connected(respx.mock)
    chats = [
        {
            "groupMetadata": {
                "id": _jid(ROOT_WA_ID),
                "subject": "Test Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(GENERAL_WA_ID),
                "subject": "General",
                "isParentGroup": False,
                "parentGroup": _jid(ROOT_WA_ID),
                "announce": False,
            }
        },
    ]
    respx.mock.post(_list_chats_url()).respond(200, json=chats)
    respx.mock.get(_group_members_url(GENERAL_WA_ID)).respond(500, json={"error": "boom"})

    provider = _provider()
    with pytest.raises(WhatsAppProviderUnavailableError):
        provider.get_group(GENERAL_WA_ID)


@respx.mock
def test_get_members_raises_provider_unavailable_on_get_messages_failure():
    """`_fetch_last_message_by_author` (called from within `_build_memberships`
    after `group-members`/`group-admins` succeed) must translate its own
    transport failure the same way."""
    _mock_token_and_connected(respx.mock)
    chats = [
        {
            "groupMetadata": {
                "id": _jid(ROOT_WA_ID),
                "subject": "Test Community",
                "isParentGroup": True,
                "parentGroup": None,
                "announce": False,
            }
        },
        {
            "groupMetadata": {
                "id": _jid(GENERAL_WA_ID),
                "subject": "General",
                "isParentGroup": False,
                "parentGroup": _jid(ROOT_WA_ID),
                "announce": False,
            }
        },
    ]
    respx.mock.post(_list_chats_url()).respond(200, json=chats)
    respx.mock.get(_group_members_url(GENERAL_WA_ID)).respond(
        200, json=[{"id": {"_serialized": MEMBER_JID}, "pushname": "Alice"}]
    )
    respx.mock.get(_group_admins_url(GENERAL_WA_ID)).respond(200, json=[])
    respx.mock.get(_get_messages_url(GENERAL_WA_ID)).mock(side_effect=httpx.ConnectError("connection refused"))

    provider = _provider()
    with pytest.raises(WhatsAppProviderUnavailableError):
        provider.get_members(GENERAL_WA_ID)


def _group_invite_link_url(wa_id: str) -> str:
    return f"{BASE_URL}/api/{SESSION}/group-invite-link/{wa_id}"


@respx.mock
def test_get_group_invite_link_returns_link_on_success():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_group_invite_link_url(GENERAL_WA_ID)).respond(
        200, json={"status": "success", "response": "https://chat.whatsapp.com/ABC123"}
    )

    provider = _provider()

    assert provider.get_group_invite_link(GENERAL_WA_ID) == "https://chat.whatsapp.com/ABC123"


@respx.mock
def test_get_group_invite_link_returns_none_on_wppconnect_error_status():
    """A real, observed live failure mode: WPPConnect returns a 500 with
    `{"status": "error", ...}` for a group the connected account can't
    generate a link for — never raised, degrades to `None`."""
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_group_invite_link_url(GENERAL_WA_ID)).respond(
        500, json={"status": "error", "message": "Error on get group invite link"}
    )

    provider = _provider()

    assert provider.get_group_invite_link(GENERAL_WA_ID) is None


@respx.mock
def test_get_group_invite_link_returns_none_on_transport_error():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_group_invite_link_url(GENERAL_WA_ID)).mock(side_effect=httpx.ConnectError("connection refused"))

    provider = _provider()

    assert provider.get_group_invite_link(GENERAL_WA_ID) is None


def _send_message_url(session: str = SESSION) -> str:
    return f"{BASE_URL}/api/{session}/send-message"


@respx.mock
def test_send_text_message_extracts_id_from_real_confirmed_response_shape():
    """The exact response shape confirmed live against a real WPPConnect
    Server (2026-08-31): `response` is a list containing the full sent
    message object, with a plain-string `id` — not a bare dict, and not a
    nested `{"_serialized": ...}` object, both of which an earlier version
    of this method's extraction logic assumed and so always missed."""
    _mock_token_and_connected(respx.mock)
    respx.mock.post(_send_message_url()).respond(
        201,
        json={
            "status": "success",
            "response": [
                {
                    "id": "true_228007130198135@lid_3EB068D9C450763680E0D5",
                    "body": "hello",
                    "type": "chat",
                    "fromMe": True,
                    "chatId": "228007130198135@lid",
                }
            ],
        },
    )

    provider = _provider()

    message_id = provider.send_text_message("228007130198135@lid", "hello")

    assert message_id == "true_228007130198135@lid_3EB068D9C450763680E0D5"


@respx.mock
def test_send_text_message_returns_none_when_no_id_found():
    _mock_token_and_connected(respx.mock)
    respx.mock.post(_send_message_url()).respond(201, json={"status": "success", "response": []})

    provider = _provider()

    assert provider.send_text_message("228007130198135@lid", "hello") is None


@respx.mock
def test_send_text_message_raises_on_transport_error():
    _mock_token_and_connected(respx.mock)
    respx.mock.post(_send_message_url()).mock(side_effect=httpx.ConnectError("connection refused"))

    provider = _provider()

    with pytest.raises(WhatsAppProviderUnavailableError):
        provider.send_text_message("228007130198135@lid", "hello")
