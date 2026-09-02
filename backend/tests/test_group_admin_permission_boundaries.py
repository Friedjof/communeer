"""HTTP-level enumeration of `group_admin` permission boundaries — the
security-critical verification for the whole feature (see `authz.py`,
`auth/provisioning.py`, `auth/claim_service.py`): a missed route here is a
real vulnerability, not just a missing feature.

Both mock communities ("Unity Alpha" and "Riverside Collective") are already
synced at app startup (`main.py::_seed_and_prime_data`), which auto-
provisions an unclaimed `group_admin` account for every admin membership —
this file claims a handful of those accounts (each used by exactly one test,
since claiming is a one-way, one-time operation on the shared test-session
database) and drives the full HTTP surface as that freshly-claimed user.
"""

import re
import uuid

import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.db import SessionLocal
from communeer.models import (
    Community,
    Group,
    GroupMembership,
    Member,
    MembershipStatus,
    User,
)
from communeer.providers.whatsapp import get_provider

UNITY_ALPHA = "Unity Alpha"
RIVERSIDE_COLLECTIVE = "Riverside Collective"

CLAIM_PASSWORD = "claimed-password-123"


def _get_community(db: Session, name: str) -> Community:
    return db.execute(select(Community).where(Community.name == name)).scalar_one()


def _get_group(db: Session, community: Community, name: str) -> Group:
    return db.execute(
        select(Group).where(Group.community_id == community.id, Group.name == name)
    ).scalar_one()


def _get_admin_members(db: Session, group: Group) -> list[Member]:
    """All admins of `group`, in a stable order — some groups in the mock
    fixture (e.g. "Marketplace") have more than one, and each is claimed by
    at most one test in this file (claiming is a one-way operation on the
    shared test-session database), so tests needing two independent admins
    of the same group pick distinct indices here rather than both landing on
    whichever row a plain, unordered `.first()` happens to return."""
    rows = db.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(
            GroupMembership.group_id == group.id,
            GroupMembership.status == MembershipStatus.member,
            GroupMembership.is_admin.is_(True),
        )
        .order_by(Member.wa_id)
    ).all()
    return [member for _membership, member in rows]


def _get_admin_member(db: Session, group: Group) -> Member:
    return _get_admin_members(db, group)[0]


def _member_id_in_group_not_in_other(
    db: Session, group_a: Group, group_b: Group, *, non_admin_only: bool = False
) -> uuid.UUID:
    a_query = select(GroupMembership.member_id).where(GroupMembership.group_id == group_a.id)
    if non_admin_only:
        a_query = a_query.where(GroupMembership.is_admin.is_(False), GroupMembership.is_super_admin.is_(False))
    a_ids = set(db.execute(a_query).scalars())
    b_ids = set(db.execute(select(GroupMembership.member_id).where(GroupMembership.group_id == group_b.id)).scalars())
    only_a = a_ids - b_ids
    assert only_a, f"expected a member in {group_a.name!r} but not {group_b.name!r}"
    return next(iter(only_a))


def _approve(wa_id: str) -> None:
    """Test-only shortcut for the `is_approved` half of what
    `POST /users/{id}/approve` (`test_users.py`) does — the app-boot priming
    step (`main.py::_seed_and_prime_data`) auto-provisions every admin
    membership across both mock communities, but (see `auth/provisioning.py`'s
    module docstring) never sends anything and never approves — every
    account this file claims needs an explicit approval first, same as a
    real owner would give via the Users page."""
    db = SessionLocal()
    try:
        member = db.execute(select(Member).where(Member.wa_id == wa_id)).scalar_one()
        user = db.execute(select(User).where(User.member_id == member.id)).scalar_one()
        user.is_approved = True
        db.commit()
    finally:
        db.close()


def _last_sent_otp_code(target_wa_id: str) -> str:
    """A fresh `/claim/request` against an already-recently-sent account
    silently no-ops under the shared resend cooldown (no oracle) rather than
    sending a new one — so the message this test cares about isn't reliably
    the *last* one the provider ever sent overall, only the last one sent to
    `target_wa_id`."""
    provider = get_provider()
    for sent_wa_id, message in reversed(provider._sent_messages):
        if sent_wa_id == target_wa_id:
            match = re.search(r"\b(\d{6})\b", message)
            assert match is not None, f"no 6-digit code found in sent message: {message!r}"
            return match.group(1)
    raise AssertionError(f"no message was ever sent to {target_wa_id!r}")


def _claim_and_enable_totp(client, wa_id: str, *, password: str = CLAIM_PASSWORD) -> None:
    """Drives the full unauthenticated-claim -> mandatory-2FA-setup flow for
    the auto-provisioned `group_admin` account linked to `wa_id`, leaving
    `client` logged in with a normal, fully-authenticated session — exactly
    the state every other assertion in this file needs to start from.

    Takes a plain `wa_id` string rather than a `Member` ORM object on
    purpose: callers fetch that object from a `db_session` that's closed
    (and, in one case, committed by an intervening service call) well before
    this runs, and a closed/expired ORM instance can't be touched again."""
    _approve(wa_id)
    phone_number = f"+{wa_id.removesuffix('@c.us')}"

    request_response = client.post("/api/v1/auth/claim/request", json={"phoneNumber": phone_number})
    assert request_response.status_code == 204, request_response.text

    code = _last_sent_otp_code(wa_id)
    complete_response = client.post(
        "/api/v1/auth/claim/complete",
        json={"phoneNumber": phone_number, "code": code, "password": password},
    )
    assert complete_response.status_code == 200, complete_response.text
    assert "communeer_session" in client.cookies

    # Freshly claimed = neither 2FA factor enabled yet — every other route
    # must 428 until this is done (asserted explicitly in
    # `test_claim_then_mandatory_2fa_gate_blocks_everything_else` below).
    setup_response = client.post("/api/v1/auth/2fa/setup")
    assert setup_response.status_code == 200, setup_response.text
    secret = setup_response.json()["secret"]

    enable_response = client.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})
    assert enable_response.status_code == 200, enable_response.text


# ---------------------------------------------------------------------------
# Claim -> mandatory 2FA gate
# ---------------------------------------------------------------------------


def test_claim_then_mandatory_2fa_gate_blocks_everything_else(client):
    db = SessionLocal()
    try:
        unity = _get_community(db, UNITY_ALPHA)
        marketplace = _get_group(db, unity, "Marketplace")
        member = _get_admin_member(db, marketplace)
        wa_id = member.wa_id
        phone_number = f"+{wa_id.removesuffix('@c.us')}"
    finally:
        db.close()

    _approve(wa_id)
    request_response = client.post("/api/v1/auth/claim/request", json={"phoneNumber": phone_number})
    assert request_response.status_code == 204

    code = _last_sent_otp_code(wa_id)
    complete_response = client.post(
        "/api/v1/auth/claim/complete",
        json={"phoneNumber": phone_number, "code": code, "password": CLAIM_PASSWORD},
    )
    assert complete_response.status_code == 200, complete_response.text

    # Neither factor enabled yet — blocked everywhere except the exempt
    # session/logout/2fa-setup paths (see `deps.py::_TOTP_SETUP_EXEMPT_PATHS`).
    blocked_response = client.get(f"/api/v1/groups/{marketplace.id}")
    assert blocked_response.status_code == 428
    assert blocked_response.json()["error"]["code"] == "totp_setup_required"

    # `/session` stays reachable (exempt) throughout.
    session_response = client.get("/api/v1/session")
    assert session_response.status_code == 200
    assert session_response.json()["role"] == "group_admin"

    setup_response = client.post("/api/v1/auth/2fa/setup")
    assert setup_response.status_code == 200
    secret = setup_response.json()["secret"]
    enable_response = client.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})
    assert enable_response.status_code == 200

    # Now unblocked, and correctly scoped to their own group.
    unblocked_response = client.get(f"/api/v1/groups/{marketplace.id}")
    assert unblocked_response.status_code == 200


# ---------------------------------------------------------------------------
# Own-group access vs. a sibling group in the same community
# ---------------------------------------------------------------------------


def test_group_admin_own_group_routes_return_200_and_sibling_group_403s(client):
    db = SessionLocal()
    try:
        unity = _get_community(db, UNITY_ALPHA)
        marketplace = _get_group(db, unity, "Marketplace")
        events = _get_group(db, unity, "Events")
        # Marketplace has two admins in the fixture; index 1 here so this
        # doesn't collide with the one `test_claim_then_mandatory_2fa_gate_...`
        # already claimed (index 0).
        member_wa_id = _get_admin_members(db, marketplace)[1].wa_id
    finally:
        db.close()

    _claim_and_enable_totp(client, member_wa_id)

    # Own group: full read access, plus the `_require_manager`-gated
    # invite-link route (owner/admin/group_admin only — a viewer 403s here,
    # tested elsewhere). Deliberately not exercising `approve`/`reject` here:
    # those call through to the shared, session-wide `MockWhatsAppProvider`
    # singleton and would permanently mutate this fixture's pending-request
    # count, which several other test files hardcode (`test_api.py`,
    # `test_growth_snapshots.py`) — that behavior is already covered against
    # an isolated `db_session` in `test_group_membership.py`.
    assert client.get(f"/api/v1/groups/{marketplace.id}").status_code == 200
    assert client.get(f"/api/v1/groups/{marketplace.id}/members").status_code == 200
    assert client.get(f"/api/v1/groups/{marketplace.id}/requests").status_code == 200
    assert client.get(f"/api/v1/groups/{marketplace.id}/invite-link").status_code == 200

    # A sibling group in the *same* community they don't administer: 403,
    # not 404 — existence of the group isn't the secret, access is.
    assert client.get(f"/api/v1/groups/{events.id}").status_code == 403
    assert client.get(f"/api/v1/groups/{events.id}/members").status_code == 403
    assert client.get(f"/api/v1/groups/{events.id}/requests").status_code == 403
    assert client.get(f"/api/v1/groups/{events.id}/invite-link").status_code == 403


# ---------------------------------------------------------------------------
# Community-level scoping (derived from administered groups) + cross-
# community isolation
# ---------------------------------------------------------------------------


def test_group_admin_community_scoping_and_cross_community_403(client):
    db = SessionLocal()
    try:
        unity = _get_community(db, UNITY_ALPHA)
        riverside = _get_community(db, RIVERSIDE_COLLECTIVE)
        events = _get_group(db, unity, "Events")
        marketplace = _get_group(db, unity, "Marketplace")
        general = _get_group(db, unity, "General")
        member_wa_id = _get_admin_member(db, events).wa_id
    finally:
        db.close()

    _claim_and_enable_totp(client, member_wa_id)

    # Own community: reachable, and every group listing/read is narrowed to
    # only the group(s) this account actually administers (Events, plus
    # Announcements — every per-group admin is also admin of the
    # announcement group in this fixture).
    assert client.get(f"/api/v1/communities/{unity.id}").status_code == 200

    groups_response = client.get(f"/api/v1/communities/{unity.id}/groups")
    assert groups_response.status_code == 200
    returned_group_ids = {g["id"] for g in groups_response.json()}
    assert str(events.id) in returned_group_ids
    assert str(marketplace.id) not in returned_group_ids
    assert str(general.id) not in returned_group_ids

    assert client.get(f"/api/v1/communities/{unity.id}/members").status_code == 200
    assert client.get(f"/api/v1/communities/{unity.id}/history").status_code == 200
    assert client.get(f"/api/v1/communities/{unity.id}/groups/history").status_code == 200

    sync_response = client.post(f"/api/v1/communities/{unity.id}/sync")
    assert sync_response.status_code == 200, sync_response.text

    # A totally unrelated community: 403 across the board.
    assert client.get(f"/api/v1/communities/{riverside.id}").status_code == 403
    assert client.get(f"/api/v1/communities/{riverside.id}/groups").status_code == 403
    assert client.get(f"/api/v1/communities/{riverside.id}/members").status_code == 403
    assert client.post(f"/api/v1/communities/{riverside.id}/sync").status_code == 403

    # `GET /communities` (the list) is filtered too — Riverside must not
    # appear for this account.
    list_response = client.get("/api/v1/communities")
    assert list_response.status_code == 200
    listed_ids = {c["id"] for c in list_response.json()}
    assert str(unity.id) in listed_ids
    assert str(riverside.id) not in listed_ids


# ---------------------------------------------------------------------------
# Renewal campaigns: `campaign_id`-only routes resolve group scope via the
# campaign itself, not a path param
# ---------------------------------------------------------------------------


def test_group_admin_renewals_scoped_to_own_group(client):
    db = SessionLocal()
    try:
        unity = _get_community(db, UNITY_ALPHA)
        general = _get_group(db, unity, "General")
        events = _get_group(db, unity, "Events")
        member = _get_admin_member(db, general)
        # `create_renewal_campaign` below commits, which (with the default
        # `expire_on_commit=True`) expires every attribute on every ORM
        # object still attached to `db` — capture plain values now, before
        # that happens, rather than after `db.close()` makes them
        # unrefreshable.
        member_wa_id = member.wa_id
        general_id = general.id
        events_id = events.id
        own_group_member_id = _member_id_in_group_not_in_other(db, general, events, non_admin_only=True)

        # Build a campaign in a group this account does *not* administer,
        # directly against the shared app DB, so its `campaign_id` exists
        # before the claimed session ever touches the API.
        from communeer.providers.whatsapp.mock import MockWhatsAppProvider
        from communeer.renewals.service import create_renewal_campaign

        events_member_id = _member_id_in_group_not_in_other(db, events, general, non_admin_only=True)
        foreign_campaign = create_renewal_campaign(
            db, MockWhatsAppProvider(), events, member_ids=[events_member_id], deadline_days=14, actor_user_id=None
        )
        foreign_campaign_id = foreign_campaign.id
    finally:
        db.close()

    _claim_and_enable_totp(client, member_wa_id)

    # Own group: allowed to create and then act on the resulting campaign.
    create_response = client.post(
        f"/api/v1/groups/{general_id}/renewals",
        json={"memberIds": [str(own_group_member_id)], "deadlineDays": 14},
    )
    assert create_response.status_code == 200, create_response.text
    own_campaign_id = create_response.json()["id"]

    assert client.get(f"/api/v1/groups/{general_id}/renewals").status_code == 200
    assert client.get(f"/api/v1/groups/{general_id}/renewals/suggestions").status_code == 200
    assert client.get(f"/api/v1/renewals/{own_campaign_id}").status_code == 200
    assert client.post(f"/api/v1/renewals/{own_campaign_id}/archive").status_code == 200

    # A group they don't administer: 403 on both the `group_id`-keyed create
    # route and the `campaign_id`-keyed routes for a pre-existing campaign
    # there.
    create_foreign_response = client.post(
        f"/api/v1/groups/{events_id}/renewals",
        json={"memberIds": [str(events_member_id)], "deadlineDays": 14},
    )
    assert create_foreign_response.status_code == 403
    assert client.get(f"/api/v1/groups/{events_id}/renewals").status_code == 403
    assert client.get(f"/api/v1/renewals/{foreign_campaign_id}").status_code == 403
    assert client.post(f"/api/v1/renewals/{foreign_campaign_id}/archive").status_code == 403


# ---------------------------------------------------------------------------
# Member detail: scoped to shared groups only
# ---------------------------------------------------------------------------


def test_group_admin_member_detail_scoped_to_shared_groups(client):
    db = SessionLocal()
    try:
        unity = _get_community(db, UNITY_ALPHA)
        riverside = _get_community(db, RIVERSIDE_COLLECTIVE)
        # Riverside's "Neighbors" — distinct from every group/admin claimed
        # by the other tests in this file, since claiming is one-way.
        neighbors = _get_group(db, riverside, "Neighbors")
        riverside_announcements = _get_group(db, riverside, "Announcements")
        general = _get_group(db, unity, "General")
        member_wa_id = _get_admin_member(db, neighbors).wa_id
        shared_member_id = _member_id_in_group_not_in_other(
            db, neighbors, general, non_admin_only=True
        )  # a real member of the caller's own group (not the caller themself)
        # Every group admin in this fixture also administers the
        # Announcements group of their own community (see `mock.py`'s
        # `riverside_group_admin_ids`), so a member is only genuinely
        # *outside* this caller's reach if they're in neither Neighbors nor
        # Riverside's Announcements — i.e. a different community entirely.
        outside_member_id = _member_id_in_group_not_in_other(db, general, neighbors)
    finally:
        db.close()

    _claim_and_enable_totp(client, member_wa_id)

    own_group_response = client.get(f"/api/v1/members/{shared_member_id}")
    assert own_group_response.status_code == 200
    # Every membership row returned must be for a group this caller actually
    # administers (Neighbors and/or Announcements) — no incidental leakage
    # of the member's activity in unrelated groups.
    administered_ids = {str(neighbors.id), str(riverside_announcements.id)}
    for membership in own_group_response.json()["memberships"]:
        assert membership["groupId"] in administered_ids

    assert client.get(f"/api/v1/members/{outside_member_id}").status_code == 403


# ---------------------------------------------------------------------------
# Owner/admin-only surfaces stay off-limits; `/whatsapp/status` stays open
# ---------------------------------------------------------------------------


def test_group_admin_cannot_access_owner_admin_only_surfaces(client):
    db = SessionLocal()
    try:
        riverside = _get_community(db, RIVERSIDE_COLLECTIVE)
        buy_sell = _get_group(db, riverside, "Buy & Sell")
        member_wa_id = _get_admin_member(db, buy_sell).wa_id
    finally:
        db.close()

    _claim_and_enable_totp(client, member_wa_id)

    assert client.get(f"/api/v1/communities/{riverside.id}/moderation/queue").status_code == 403
    assert client.get("/api/v1/audit").status_code == 403
    assert client.get("/api/v1/users").status_code == 403
    assert client.post("/api/v1/whatsapp/connect").status_code == 403
    assert client.post("/api/v1/whatsapp/discover-and-sync").status_code == 403

    # Global, harmless connection status stays reachable for everyone.
    assert client.get("/api/v1/whatsapp/status").status_code == 200

    # But this account's own community/group remain fully usable.
    assert client.get(f"/api/v1/communities/{riverside.id}").status_code == 200
    assert client.get(f"/api/v1/groups/{buy_sell.id}").status_code == 200
