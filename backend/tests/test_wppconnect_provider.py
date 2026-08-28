"""Unit tests for `WppconnectProvider`, mocking the WPPConnect Server's HTTP
API with `respx` shaped per the plan's documented (unverified-against-real-
data) hypothesis: `list-chats` embeds `groupMetadata.isParentGroup` /
`parentGroup` / `announce`. These tests only prove the parsing/derivation
logic is correct *given* that shape — they do not (and cannot) prove the
hypothesis itself holds against a real WPPConnect Server.
"""

import httpx
import pytest
import respx

from communeer.config import Settings
from communeer.providers.whatsapp.base import WhatsAppNotConnectedError
from communeer.providers.whatsapp.wppconnect import WppconnectProvider

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

    own_lid = "236794549432473@lid"
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
def test_get_admin_community_wa_ids_returns_none_when_not_connected():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_status_session_url()).respond(200, json={"status": "CLOSED"})

    provider = _provider()

    assert provider.get_own_wa_id() is None
    assert provider.get_admin_community_wa_ids() is None


@respx.mock
def test_get_connection_status_never_raises_on_transport_error():
    respx.mock.post(_generate_token_url()).respond(200, json={"token": "test-token"})
    respx.mock.get(_status_session_url()).mock(side_effect=httpx.ConnectError("connection refused"))

    provider = _provider()
    status = provider.get_connection_status()

    assert status.state.value == "error"
    assert status.detail is not None
    assert "connection refused" in status.detail
