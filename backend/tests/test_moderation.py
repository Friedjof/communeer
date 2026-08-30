import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import event, select

from communeer.communities.service import get_group_admin_count, list_community_members
from communeer.errors import ApiError
from communeer.models import (
    Community,
    Group,
    GroupMembership,
    MembershipStatus,
    ModerationDismissal,
)
from communeer.moderation.service import (
    CAPACITY_ATTENTION_THRESHOLD,
    JOIN_BURST_MIN_ABSOLUTE,
    JOIN_BURST_MIN_FRACTION,
    JOIN_BURST_WINDOW,
    dismiss_moderation_item,
    get_admin_coverage_gaps,
    get_capacity_attention_groups,
    get_join_burst_groups,
    get_moderation_queue,
    get_never_active_members,
)
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"
RIVERSIDE_WA_ID = "120363020000000001@g.us"


class _ScopedMockProvider(MockWhatsAppProvider):
    """Same fixture data as `MockWhatsAppProvider`, but with a scripted
    `get_admin_community_wa_ids()` answer — the real mock provider always
    returns `None` (no filtering), which can't exercise the "not an admin
    community" branch on its own."""

    def __init__(self, admin_wa_ids: set[str] | None) -> None:
        super().__init__()
        self._admin_wa_ids_override = admin_wa_ids

    def get_admin_community_wa_ids(self) -> set[str] | None:
        return self._admin_wa_ids_override


def _sync_unity(db_session) -> Community:
    provider = MockWhatsAppProvider()
    return sync_community(db_session, provider, UNITY_WA_ID)


@contextmanager
def _count_queries(db_session):
    """Counts SQL statements issued through `db_session`'s engine for the
    duration of the `with` block — used to assert the batched
    admin-coverage/join-burst queries stay O(1) in the number of groups
    instead of O(group_count)."""
    engine = db_session.get_bind()
    counter = {"n": 0}

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)


# ---------------------------------------------------------------------------
# admin_coverage_gaps
# ---------------------------------------------------------------------------


def test_admin_coverage_gaps_flags_only_groups_at_or_below_one_admin(db_session):
    community = _sync_unity(db_session)

    gaps = get_admin_coverage_gaps(db_session, community)

    groups = {g.name: g for g in db_session.execute(select(Group).where(Group.community_id == community.id)).scalars()}
    expected_flagged = {
        name for name, g in groups.items() if get_group_admin_count(db_session, g.id) <= 1
    }
    assert {gap.group_name for gap in gaps} == expected_flagged
    assert expected_flagged  # the mock fixture has at least one single-admin group (General, Events)
    for gap in gaps:
        assert gap.admin_count <= 1
        assert gap.admin_count == get_group_admin_count(db_session, groups[gap.group_name].id)


def test_admin_coverage_gaps_handles_group_with_zero_memberships(db_session):
    """A group with no memberships at all has no row in the batched
    grouped-count query — must default to `admin_count == 0` (and thus show
    up as a gap), not crash or get silently skipped."""
    community = _sync_unity(db_session)
    empty_group = Group(
        community_id=community.id,
        wa_id="empty-group@g.us",
        name="Empty Group",
        member_count=0,
    )
    db_session.add(empty_group)
    db_session.commit()

    gaps = get_admin_coverage_gaps(db_session, community)
    empty_gap = next(g for g in gaps if g.group_id == empty_group.id)
    assert empty_gap.admin_count == 0


def test_admin_coverage_gaps_query_count_does_not_scale_with_group_count(db_session):
    """The batched rewrite must issue a small, fixed number of queries
    (dismissals + groups + one grouped admin-count query) regardless of how
    many groups the community has, instead of the old one-query-per-group
    approach."""
    community = _sync_unity(db_session)
    group_count = len(
        list(db_session.execute(select(Group).where(Group.community_id == community.id)).scalars())
    )
    assert group_count >= 3  # the mock fixture has several groups already

    with _count_queries(db_session) as counter:
        get_admin_coverage_gaps(db_session, community)

    assert counter["n"] <= 3
    assert counter["n"] < group_count


# ---------------------------------------------------------------------------
# never_active_members
# ---------------------------------------------------------------------------


def test_never_active_members_excludes_admins_and_matches_manual_filter(db_session):
    community = _sync_unity(db_session)

    never_active = get_never_active_members(db_session, community)

    all_members = list_community_members(db_session, community)
    expected_ids = {
        a.member.id
        for a in all_members
        if not a.is_admin and not a.is_community_admin and a.last_message_at is None
    }
    assert {a.member.id for a in never_active} == expected_ids
    assert expected_ids  # the mock fixture deliberately produces "never posted" members

    for agg in never_active:
        assert not agg.is_admin
        assert not agg.is_community_admin
        assert agg.last_message_at is None


# ---------------------------------------------------------------------------
# join_bursts
# ---------------------------------------------------------------------------


def test_join_burst_groups_empty_when_no_recent_joins(db_session):
    """The mock fixture's `joined_at` values are all seeded relative to a
    fixed `_NOW` in the past (2026-08-01), so against the real wall clock
    none of them fall inside the last 24h — no group should qualify."""
    community = _sync_unity(db_session)
    assert get_join_burst_groups(db_session, community) == []


def test_join_burst_flags_group_with_a_recent_join_spike(db_session):
    community = _sync_unity(db_session)
    general = db_session.execute(select(Group).where(Group.name == "General")).scalar_one()

    memberships = list(
        db_session.execute(
            select(GroupMembership).where(
                GroupMembership.group_id == general.id, GroupMembership.status == MembershipStatus.member
            )
        ).scalars()
    )
    member_count = len(memberships)
    assert member_count > 0

    # Push enough memberships' joined_at into the last 24h to clear both the
    # fraction and absolute thresholds, simulating a real join-burst.
    now = datetime.now(UTC)
    burst_count = max(JOIN_BURST_MIN_ABSOLUTE, int(member_count * JOIN_BURST_MIN_FRACTION) + 1)
    for membership in memberships[:burst_count]:
        membership.joined_at = now - (JOIN_BURST_WINDOW / 2)
    db_session.commit()

    bursts = get_join_burst_groups(db_session, community)

    assert any(b.group_id == general.id for b in bursts)
    general_burst = next(b for b in bursts if b.group_id == general.id)
    assert general_burst.recent_join_count == burst_count
    assert general_burst.member_count == member_count
    assert general_burst.recent_join_count / general_burst.member_count >= JOIN_BURST_MIN_FRACTION


def test_join_burst_does_not_flag_below_absolute_minimum_even_at_high_fraction(db_session):
    """A brand-new, still-tiny group where a couple of members joined
    "recently" must not be flagged just because that's a high fraction of a
    near-zero base — the absolute minimum guards against exactly this."""
    community = _sync_unity(db_session)
    events = db_session.execute(select(Group).where(Group.name == "Events")).scalar_one()

    memberships = list(
        db_session.execute(
            select(GroupMembership).where(
                GroupMembership.group_id == events.id, GroupMembership.status == MembershipStatus.member
            )
        ).scalars()
    )

    now = datetime.now(UTC)
    tiny_recent_count = min(2, JOIN_BURST_MIN_ABSOLUTE - 1)
    assert tiny_recent_count < JOIN_BURST_MIN_ABSOLUTE
    for membership in memberships[:tiny_recent_count]:
        membership.joined_at = now - (JOIN_BURST_WINDOW / 2)
    # remove every other membership so the fraction would otherwise be huge
    for membership in memberships[tiny_recent_count:]:
        db_session.delete(membership)
    db_session.commit()

    bursts = get_join_burst_groups(db_session, community)
    assert not any(b.group_id == events.id for b in bursts)


def test_join_burst_groups_skips_group_with_zero_memberships(db_session):
    """A group with no `member`-status memberships at all has no entry in
    the batched `joined_at`-by-group query — must be treated as an empty
    list (0 members), which the existing `member_count == 0: continue` guard
    already excludes from the result, not a crash."""
    community = _sync_unity(db_session)
    empty_group = Group(
        community_id=community.id,
        wa_id="empty-group-burst@g.us",
        name="Empty Burst Group",
        member_count=0,
    )
    db_session.add(empty_group)
    db_session.commit()

    bursts = get_join_burst_groups(db_session, community)
    assert not any(b.group_id == empty_group.id for b in bursts)


def test_join_burst_groups_query_count_does_not_scale_with_group_count(db_session):
    """Same O(1)-queries guarantee as admin-coverage-gaps above: dismissals +
    groups + one batched `joined_at` query, regardless of group count."""
    community = _sync_unity(db_session)
    group_count = len(
        list(db_session.execute(select(Group).where(Group.community_id == community.id)).scalars())
    )
    assert group_count >= 3

    with _count_queries(db_session) as counter:
        get_join_burst_groups(db_session, community)

    assert counter["n"] <= 3
    assert counter["n"] < group_count


# ---------------------------------------------------------------------------
# capacity_attention
# ---------------------------------------------------------------------------


def test_capacity_attention_flags_marketplace_and_pending_groups(db_session):
    community = _sync_unity(db_session)

    attention = get_capacity_attention_groups(db_session, community)
    by_name = {a.group_name: a for a in attention}

    groups = {g.name: g for g in db_session.execute(select(Group).where(Group.community_id == community.id)).scalars()}
    marketplace = groups["Marketplace"]
    # spec fixture: Marketplace is 981/1024 ~ 95.8% full, above the threshold.
    expected_percent = round(marketplace.member_count / marketplace.member_limit * 1000) / 10
    assert expected_percent >= CAPACITY_ATTENTION_THRESHOLD
    assert "Marketplace" in by_name
    assert by_name["Marketplace"].percent_full == expected_percent
    assert by_name["Marketplace"].reason in ("capacity", "both")

    # Marketplace also has 3 pending requests in the fixture -> reason "both".
    assert marketplace.pending_request_count > 0
    assert by_name["Marketplace"].reason == "both"
    assert by_name["Marketplace"].pending_request_count == marketplace.pending_request_count

    # Every group actually returned must satisfy at least one real reason.
    for a in attention:
        group = groups[a.group_name]
        is_capacity = a.percent_full is not None and a.percent_full >= CAPACITY_ATTENTION_THRESHOLD
        is_requests = a.pending_request_count > 0
        assert is_capacity or is_requests
        assert a.pending_request_count == group.pending_request_count


def test_capacity_attention_excludes_groups_with_no_limit_and_no_pending(db_session):
    community = _sync_unity(db_session)
    attention = get_capacity_attention_groups(db_session, community)
    # General has a high member_limit (1024) with 180 members and no pending
    # requests -> must not show up.
    assert not any(a.group_name == "General" for a in attention)


# ---------------------------------------------------------------------------
# dismiss_moderation_item
# ---------------------------------------------------------------------------


def test_dismiss_admin_coverage_gap_removes_it_then_reappears_when_worse(db_session):
    community = _sync_unity(db_session)
    gaps_before = get_admin_coverage_gaps(db_session, community)
    # Pick a target with exactly one admin so it can get strictly worse (0
    # admins) below.
    target = next(g for g in gaps_before if g.admin_count == 1)

    dismiss_moderation_item(
        db_session,
        community,
        MockWhatsAppProvider(),
        "admin_coverage_gaps",
        str(target.group_id),
        reason="handled manually",
        actor_user_id=None,
    )

    gaps_after = get_admin_coverage_gaps(db_session, community)
    assert target.group_id not in {g.group_id for g in gaps_after}

    # Worsen: remove the group's one remaining admin.
    memberships = list(
        db_session.execute(
            select(GroupMembership).where(
                GroupMembership.group_id == target.group_id, GroupMembership.is_admin.is_(True)
            )
        ).scalars()
    )
    for membership in memberships:
        membership.is_admin = False
    db_session.commit()

    gaps_worsened = get_admin_coverage_gaps(db_session, community)
    reappeared = next((g for g in gaps_worsened if g.group_id == target.group_id), None)
    assert reappeared is not None
    assert reappeared.admin_count < target.admin_count


def test_dismiss_never_active_member_stays_suppressed_across_reads(db_session):
    community = _sync_unity(db_session)
    never_active_before = get_never_active_members(db_session, community)
    target = never_active_before[0]

    dismiss_moderation_item(
        db_session,
        community,
        MockWhatsAppProvider(),
        "never_active_members",
        str(target.member.id),
        reason=None,
        actor_user_id=None,
    )

    never_active_after = get_never_active_members(db_session, community)
    assert target.member.id not in {a.member.id for a in never_active_after}

    # Still suppressed on a second read (no worsening path for this section —
    # it's a binary "never posted" signal, dismissed unconditionally).
    never_active_again = get_never_active_members(db_session, community)
    assert target.member.id not in {a.member.id for a in never_active_again}


def test_dismiss_upsert_does_not_create_duplicate_row(db_session):
    community = _sync_unity(db_session)
    target = next(g for g in get_admin_coverage_gaps(db_session, community) if g.admin_count == 1)

    provider = MockWhatsAppProvider()
    dismiss_moderation_item(db_session, community, provider, "admin_coverage_gaps", str(target.group_id), reason="first", actor_user_id=None)
    dismiss_moderation_item(db_session, community, provider, "admin_coverage_gaps", str(target.group_id), reason="second", actor_user_id=None)

    rows = list(
        db_session.execute(
            select(ModerationDismissal).where(
                ModerationDismissal.community_id == community.id,
                ModerationDismissal.section == "admin_coverage_gaps",
                ModerationDismissal.target_id == str(target.group_id),
            )
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].reason == "second"


def test_dismiss_unknown_section_raises_bad_request(db_session):
    community = _sync_unity(db_session)
    target = get_admin_coverage_gaps(db_session, community)[0]

    try:
        dismiss_moderation_item(
            db_session, community, MockWhatsAppProvider(), "not_a_real_section", str(target.group_id), reason=None, actor_user_id=None
        )
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 400


def test_dismiss_target_not_in_community_raises_not_found(db_session):
    community = _sync_unity(db_session)

    try:
        dismiss_moderation_item(
            db_session,
            community,
            MockWhatsAppProvider(),
            "admin_coverage_gaps",
            str(uuid.uuid4()),
            reason=None,
            actor_user_id=None,
        )
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 404


def test_dismiss_raises_not_found_when_community_is_not_admin_community(db_session):
    """Mirrors `get_moderation_queue`'s own admin-community scoping (see
    module docstring): an owner/admin must not be able to dismiss items in a
    community the connected WhatsApp account doesn't actually administer,
    even though the app-level role check (`require_role`) alone would let
    them through."""
    community = _sync_unity(db_session)
    target = get_admin_coverage_gaps(db_session, community)[0]
    provider = _ScopedMockProvider(admin_wa_ids={RIVERSIDE_WA_ID})  # admin of a different community

    try:
        dismiss_moderation_item(
            db_session,
            community,
            provider,
            "admin_coverage_gaps",
            str(target.group_id),
            reason=None,
            actor_user_id=None,
        )
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 404

    # Nothing was actually dismissed — the item is still there.
    assert target.group_id in {g.group_id for g in get_admin_coverage_gaps(db_session, community)}


# ---------------------------------------------------------------------------
# get_moderation_queue: admin-community scoping
# ---------------------------------------------------------------------------


def test_moderation_queue_returns_data_when_provider_says_none_means_no_filtering(db_session):
    community = _sync_unity(db_session)
    provider = _ScopedMockProvider(admin_wa_ids=None)

    queue = get_moderation_queue(db_session, community, provider)

    assert queue.admin_coverage_gaps or queue.never_active_members  # real data, not fabricated-empty


def test_moderation_queue_returns_all_empty_when_community_is_not_admin_community(db_session):
    community = _sync_unity(db_session)
    # Admin of some *other* community, not this one.
    provider = _ScopedMockProvider(admin_wa_ids={RIVERSIDE_WA_ID})

    queue = get_moderation_queue(db_session, community, provider)

    assert queue.admin_coverage_gaps == []
    assert queue.never_active_members == []
    assert queue.join_bursts == []
    assert queue.capacity_attention == []


def test_moderation_queue_returns_data_when_community_is_in_admin_set(db_session):
    community = _sync_unity(db_session)
    provider = _ScopedMockProvider(admin_wa_ids={UNITY_WA_ID})

    queue = get_moderation_queue(db_session, community, provider)

    assert queue.admin_coverage_gaps
    assert queue.never_active_members


# ---------------------------------------------------------------------------
# HTTP-level tests
# ---------------------------------------------------------------------------


def _login(client) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "changeme123"})
    assert response.status_code == 200


def test_moderation_route_requires_auth(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/v1/communities/{fake_id}/moderation/queue")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_moderation_route_404_for_unknown_community(client):
    _login(client)
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/communities/{fake_id}/moderation/queue").status_code == 404


def test_moderation_queue_endpoint_end_to_end(client):
    _login(client)

    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")

    response = client.get(f"/api/v1/communities/{unity_alpha['id']}/moderation/queue")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"adminCoverageGaps", "neverActiveMembers", "joinBursts", "capacityAttention"}

    assert len(body["adminCoverageGaps"]) > 0
    for row in body["adminCoverageGaps"]:
        assert row["adminCount"] <= 1
        assert "groupId" in row and "groupName" in row

    assert len(body["neverActiveMembers"]) > 0
    members = client.get(f"/api/v1/communities/{unity_alpha['id']}/members").json()
    admin_ids = {m["id"] for m in members if m["isAdmin"] or m["isCommunityAdmin"]}
    for row in body["neverActiveMembers"]:
        assert row["memberId"] not in admin_ids

    assert len(body["capacityAttention"]) > 0
    groups = client.get(f"/api/v1/communities/{unity_alpha['id']}/groups").json()
    marketplace = next(g for g in groups if g["name"] == "Marketplace")
    marketplace_row = next(r for r in body["capacityAttention"] if r["groupName"] == "Marketplace")
    assert marketplace_row["pendingRequestCount"] == marketplace["pendingRequestCount"]

    # join bursts: real wall clock is far past the mock fixture's fixed `_NOW`
    # anchor, so no group should show a recent-join spike against live data.
    assert body["joinBursts"] == []


def _seed_viewer_user() -> None:
    """Creates a `viewer`-role user directly via the DB, bypassing the
    normal (owner-only, not yet built) user-management flow — there's no
    signup endpoint, so this is the same "insert directly for a test" pattern
    the task's own verification plan calls for."""
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


def test_viewer_role_gets_403_on_audit_and_moderation_but_owner_gets_200(client):
    _seed_viewer_user()

    viewer_login = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-123"})
    assert viewer_login.status_code == 200
    assert viewer_login.json()["role"] == "viewer"

    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")

    audit_response = client.get("/api/v1/audit")
    assert audit_response.status_code == 403
    assert audit_response.json()["error"]["code"] == "forbidden"

    moderation_response = client.get(f"/api/v1/communities/{unity_alpha['id']}/moderation/queue")
    assert moderation_response.status_code == 403
    assert moderation_response.json()["error"]["code"] == "forbidden"

    client.post("/api/v1/auth/logout")
    _login(client)  # back to the owner seed user

    assert client.get("/api/v1/audit").status_code == 200
    assert client.get(f"/api/v1/communities/{unity_alpha['id']}/moderation/queue").status_code == 200


# ---------------------------------------------------------------------------
# HTTP-level tests: dismissals
# ---------------------------------------------------------------------------


def _get_unity_alpha(client) -> dict:
    communities = client.get("/api/v1/communities").json()
    return next(c for c in communities if c["name"] == "Unity Alpha")


def test_dismiss_endpoint_viewer_gets_403(client):
    _seed_viewer_user()
    _login(client)
    unity_alpha = _get_unity_alpha(client)
    unity_alpha_id = unity_alpha["id"]
    queue = client.get(f"/api/v1/communities/{unity_alpha_id}/moderation/queue").json()
    gap = queue["adminCoverageGaps"][0]
    client.post("/api/v1/auth/logout")

    viewer_login = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-123"})
    assert viewer_login.status_code == 200

    response = client.post(
        f"/api/v1/communities/{unity_alpha_id}/moderation/dismissals",
        json={"section": "admin_coverage_gaps", "targetId": gap["groupId"], "reason": "viewer attempt"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    client.post("/api/v1/auth/logout")
    _login(client)


def test_dismiss_endpoint_invalid_section_is_rejected(client):
    _login(client)
    unity_alpha = _get_unity_alpha(client)
    queue = client.get(f"/api/v1/communities/{unity_alpha['id']}/moderation/queue").json()
    gap = queue["adminCoverageGaps"][0]

    response = client.post(
        f"/api/v1/communities/{unity_alpha['id']}/moderation/dismissals",
        json={"section": "not_a_real_section", "targetId": gap["groupId"]},
    )
    assert response.status_code == 422


def test_dismiss_endpoint_unknown_target_returns_404(client):
    _login(client)
    unity_alpha = _get_unity_alpha(client)

    response = client.post(
        f"/api/v1/communities/{unity_alpha['id']}/moderation/dismissals",
        json={"section": "admin_coverage_gaps", "targetId": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_dismiss_endpoint_removes_item_and_upsert_leaves_one_audit_and_one_row(client):
    _login(client)
    unity_alpha = _get_unity_alpha(client)
    community_id = unity_alpha["id"]

    queue_before = client.get(f"/api/v1/communities/{community_id}/moderation/queue").json()
    gap = queue_before["adminCoverageGaps"][0]

    response = client.post(
        f"/api/v1/communities/{community_id}/moderation/dismissals",
        json={"section": "admin_coverage_gaps", "targetId": gap["groupId"], "reason": "already promoted a second admin"},
    )
    assert response.status_code == 204

    queue_after = client.get(f"/api/v1/communities/{community_id}/moderation/queue").json()
    assert gap["groupId"] not in {g["groupId"] for g in queue_after["adminCoverageGaps"]}

    audit = client.get("/api/v1/audit", params={"action": "moderation.dismissed"}).json()
    matching = [e for e in audit if e["targetId"] == gap["groupId"]]
    assert len(matching) == 1
    assert matching[0]["detail"]["section"] == "admin_coverage_gaps"

    # Re-dismiss the same item (upsert path) — still exactly one audit event
    # and, at the DB level, still exactly one dismissal row for this target.
    response_again = client.post(
        f"/api/v1/communities/{community_id}/moderation/dismissals",
        json={"section": "admin_coverage_gaps", "targetId": gap["groupId"], "reason": "confirmed again"},
    )
    assert response_again.status_code == 204

    audit_again = client.get("/api/v1/audit", params={"action": "moderation.dismissed"}).json()
    matching_again = [e for e in audit_again if e["targetId"] == gap["groupId"]]
    assert len(matching_again) == 2  # one audit event per dismiss call — audit is an append-only log

    from communeer.db import SessionLocal

    db = SessionLocal()
    try:
        rows = list(
            db.execute(
                select(ModerationDismissal).where(
                    ModerationDismissal.community_id == uuid.UUID(community_id),
                    ModerationDismissal.section == "admin_coverage_gaps",
                    ModerationDismissal.target_id == gap["groupId"],
                )
            ).scalars()
        )
    finally:
        db.close()
    assert len(rows) == 1  # the dismissal row itself is upserted, not duplicated
    assert rows[0].reason == "confirmed again"


def test_dismiss_endpoint_returns_404_when_community_is_not_admin_community(client, app):
    """End-to-end version of `test_dismiss_raises_not_found_when_community_is_not_admin_community`
    above — confirms the router layer actually wires the provider through
    to `dismiss_moderation_item`, not just the service function in
    isolation."""
    from communeer.deps import get_provider

    _login(client)
    unity_alpha = _get_unity_alpha(client)
    community_id = unity_alpha["id"]

    queue = client.get(f"/api/v1/communities/{community_id}/moderation/queue").json()
    gap = queue["adminCoverageGaps"][0]

    app.dependency_overrides[get_provider] = lambda: _ScopedMockProvider(admin_wa_ids={RIVERSIDE_WA_ID})
    try:
        response = client.post(
            f"/api/v1/communities/{community_id}/moderation/dismissals",
            json={"section": "admin_coverage_gaps", "targetId": gap["groupId"]},
        )
        assert response.status_code == 404
    finally:
        del app.dependency_overrides[get_provider]

    # Nothing was dismissed — the item is still there once the override is gone.
    queue_after = client.get(f"/api/v1/communities/{community_id}/moderation/queue").json()
    assert gap["groupId"] in {g["groupId"] for g in queue_after["adminCoverageGaps"]}
