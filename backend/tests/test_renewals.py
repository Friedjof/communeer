from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import event, select

from communeer.errors import ApiError
from communeer.models import AuditEvent, Community, Group, GroupMembership
from communeer.models.renewal import (
    RenewalConfirmation,
    RenewalConfirmationStatus,
)
from communeer.providers.whatsapp.base import WhatsAppProviderUnavailableError
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.renewals.service import (
    apply_renewal_confirm_reaction,
    apply_renewal_decline_reaction,
    archive_campaign,
    build_renewal_reminder_message,
    check_renewal_reactions,
    confirm_renewal,
    create_renewal_campaign,
    delete_campaign,
    get_campaign_summaries,
    get_campaign_summary,
    get_non_responders,
    get_renewal_suggestions,
    is_confirmation_expired,
    list_campaigns_for_group,
    process_due_removals,
    remove_from_campaign,
    send_renewal_reminder,
    unarchive_campaign,
)
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"
UNITY_MARKETPLACE_WA_ID = "120363010000000010@g.us"


def _sync_unity(db_session) -> Community:
    provider = MockWhatsAppProvider()
    return sync_community(db_session, provider, UNITY_WA_ID)


def _get_group(db_session, wa_id: str) -> Group:
    return db_session.execute(select(Group).where(Group.wa_id == wa_id)).scalar_one()


def _sync_unity_marketplace(db_session) -> Group:
    """Most tests need a group with plenty of non-admin candidates and real
    activity variety — Marketplace (981 members, 2 admins) has both, and
    `db_session` is a fresh isolated DB+provider per test, so mutating it
    here (including actually removing a member) never leaks into other
    tests, unlike the shared `client` fixture (see the dedicated
    Riverside/Volunteers group used for the one HTTP-level removal test
    below, matching the same isolation concern already established for
    join-request approval elsewhere in this suite)."""
    _sync_unity(db_session)
    return _get_group(db_session, UNITY_MARKETPLACE_WA_ID)


@contextmanager
def _count_queries(db_session):
    """Counts SQL statements issued through `db_session`'s engine for the
    duration of the `with` block."""
    engine = db_session.get_bind()
    counter = {"n": 0}

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)


def test_suggestions_never_include_an_admin(db_session):
    group = _sync_unity_marketplace(db_session)

    suggestions = get_renewal_suggestions(db_session, group)

    assert len(suggestions) > 0
    for membership in suggestions:
        assert not membership.is_admin
        assert not membership.is_super_admin


def test_suggestions_sort_never_posted_members_first_then_oldest_last_message(db_session):
    """Members who have never posted (`last_message_at is None`) are the
    most likely renewal candidates and must surface first, ahead of members
    who have posted at some point — even a long time ago."""
    group = _sync_unity_marketplace(db_session)

    suggestions = get_renewal_suggestions(db_session, group)
    assert len(suggestions) > 0

    never_posted_flags = [m.last_message_at is None for m in suggestions]
    # the mock fixture deliberately produces both cases (never-posted and
    # posted) with real variety, so both groups should be non-empty here.
    assert any(never_posted_flags)
    assert not all(never_posted_flags)

    # every "never posted" row must come before every "has posted" row.
    first_posted_index = next((i for i, never in enumerate(never_posted_flags) if not never), None)
    assert first_posted_index is not None
    assert all(never_posted_flags[:first_posted_index])
    assert not any(never_posted_flags[first_posted_index:])

    # among members who have posted, oldest `last_message_at` (longest since
    # last message) sorts first.
    posted_last_message_ats = [m.last_message_at for m in suggestions if m.last_message_at is not None]
    assert posted_last_message_ats == sorted(posted_last_message_ats)


def test_creating_campaign_with_admin_member_is_rejected(db_session):
    group = _sync_unity_marketplace(db_session)

    admin_membership = db_session.execute(
        select(GroupMembership).where(GroupMembership.group_id == group.id, GroupMembership.is_admin.is_(True))
    ).scalars().first()
    assert admin_membership is not None

    try:
        create_renewal_campaign(
            db_session, MockWhatsAppProvider(), group, member_ids=[admin_membership.member_id], deadline_days=7
        )
        raised = False
    except ApiError as exc:
        raised = True
        assert exc.status_code == 400
        assert exc.code == "bad_request"

    assert raised


def test_creating_campaign_with_valid_members_creates_pending_confirmations_and_audit_event(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:3]]

    audit_count_before = db_session.execute(select(AuditEvent)).scalars().all()

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)

    assert campaign.group_id == group.id
    assert campaign.deadline > campaign.started_at

    confirmations = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalars().all()
    assert len(confirmations) == len(chosen)
    assert {c.member_id for c in confirmations} == set(chosen)
    for c in confirmations:
        assert c.status == RenewalConfirmationStatus.pending
        assert c.responded_at is None

    audit_events = db_session.execute(select(AuditEvent)).scalars().all()
    assert len(audit_events) == len(audit_count_before) + 1
    new_event = next(e for e in audit_events if e.action == "renewal.started")
    assert new_event.target_type == "group"
    assert new_event.target_id == str(group.id)
    assert new_event.detail["memberCount"] == len(chosen)
    assert new_event.detail["campaignId"] == str(campaign.id)


def test_confirming_flips_status_and_updates_campaign_counts(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:4]]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)

    counts_before = get_campaign_summary(db_session, campaign)
    assert counts_before.pending == 4
    assert counts_before.confirmed == 0
    assert counts_before.expired == 0
    assert counts_before.total == 4

    confirmation = db_session.execute(
        select(RenewalConfirmation).where(
            RenewalConfirmation.campaign_id == campaign.id,
            RenewalConfirmation.member_id == chosen[0],
        )
    ).scalar_one()
    assert confirmation.responded_at is None

    confirmed = confirm_renewal(db_session, confirmation)
    assert confirmed.status == RenewalConfirmationStatus.confirmed
    assert confirmed.responded_at is not None

    audit_events = db_session.execute(select(AuditEvent)).scalars().all()
    confirm_event = next(e for e in audit_events if e.action == "renewal.confirmed")
    assert confirm_event.target_type == "member"
    assert confirm_event.target_id == str(chosen[0])
    assert confirm_event.detail["campaignId"] == str(campaign.id)

    counts_after = get_campaign_summary(db_session, campaign)
    assert counts_after.pending == 3
    assert counts_after.confirmed == 1
    assert counts_after.expired == 0
    assert counts_after.total == 4


def test_expired_confirmation_is_computed_never_stored(db_session):
    """The whole point of this design: a confirmation past its campaign's
    deadline is reported as expired by `get_non_responders`/campaign
    summaries, but its stored `status` column must never be anything other
    than `pending` — nothing in this codebase actively transitions it."""
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:2]]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)

    # simulate time passing: push the deadline into the past directly.
    campaign.deadline = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    db_session.refresh(campaign)

    non_responders = get_non_responders(db_session, campaign)
    assert {c.member_id for c in non_responders} == set(chosen)
    for c in non_responders:
        # expiry is reported...
        assert c.status == RenewalConfirmationStatus.pending
    # ...but the stored status is untouched (re-fetch from DB to be sure this
    # isn't just an in-memory artifact).
    stored = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalars().all()
    for c in stored:
        assert c.status == RenewalConfirmationStatus.pending

    counts = get_campaign_summary(db_session, campaign)
    assert counts.expired == 2
    assert counts.pending == 0
    assert counts.confirmed == 0


def test_expired_confirmation_excludes_already_confirmed_members(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:2]]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)

    confirmation = db_session.execute(
        select(RenewalConfirmation).where(
            RenewalConfirmation.campaign_id == campaign.id,
            RenewalConfirmation.member_id == chosen[0],
        )
    ).scalar_one()
    confirm_renewal(db_session, confirmation)

    campaign.deadline = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    db_session.refresh(campaign)

    non_responders = get_non_responders(db_session, campaign)
    assert {c.member_id for c in non_responders} == {chosen[1]}

    counts = get_campaign_summary(db_session, campaign)
    assert counts.confirmed == 1
    assert counts.expired == 1
    assert counts.pending == 0


def test_get_campaign_summaries_matches_per_campaign_summary_for_multiple_campaigns(db_session):
    """The batched `get_campaign_summaries()` (used by the campaign-listing
    endpoint) must return, for every campaign, exactly the same counts as
    calling `get_campaign_summary()` once per campaign would."""
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    assert len(suggestions) >= 6

    campaign_a = create_renewal_campaign(
        db_session, MockWhatsAppProvider(), group, member_ids=[m.member_id for m in suggestions[:3]], deadline_days=7
    )
    campaign_b = create_renewal_campaign(
        db_session, MockWhatsAppProvider(), group, member_ids=[m.member_id for m in suggestions[3:6]], deadline_days=7
    )

    # confirm one member of campaign_b, and expire campaign_a entirely, so the
    # two campaigns end up with genuinely different pending/confirmed/expired
    # splits (not just two copies of the same all-pending counts).
    confirmation_b = db_session.execute(
        select(RenewalConfirmation).where(
            RenewalConfirmation.campaign_id == campaign_b.id,
            RenewalConfirmation.member_id == suggestions[3].member_id,
        )
    ).scalar_one()
    confirm_renewal(db_session, confirmation_b)

    campaign_a.deadline = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    db_session.refresh(campaign_a)
    db_session.refresh(campaign_b)

    campaigns = list_campaigns_for_group(db_session, group.id)
    assert {c.id for c in campaigns} >= {campaign_a.id, campaign_b.id}

    batched = get_campaign_summaries(db_session, campaigns)
    assert set(batched) == {c.id for c in campaigns}

    for campaign in campaigns:
        expected = get_campaign_summary(db_session, campaign)
        actual = batched[campaign.id]
        assert (actual.pending, actual.confirmed, actual.expired, actual.total) == (
            expected.pending,
            expected.confirmed,
            expected.expired,
            expected.total,
        )

    assert batched[campaign_a.id].expired == 3
    assert batched[campaign_b.id].confirmed == 1
    assert batched[campaign_b.id].pending == 2


def test_get_campaign_summaries_handles_campaign_with_zero_confirmations(db_session):
    """A campaign somehow left with no confirmation rows must still get an
    all-zero `CampaignCounts` entry, never a missing dict key or a crash."""
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    campaign = create_renewal_campaign(
        db_session, MockWhatsAppProvider(), group, member_ids=[suggestions[0].member_id], deadline_days=7
    )

    # delete the one confirmation the campaign started with, simulating a
    # campaign with zero relevant rows.
    for confirmation in db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalars():
        db_session.delete(confirmation)
    db_session.commit()

    summaries = get_campaign_summaries(db_session, [campaign])
    counts = summaries[campaign.id]
    assert (counts.pending, counts.confirmed, counts.expired, counts.total) == (0, 0, 0, 0)


def test_get_campaign_summaries_query_count_does_not_scale_with_campaign_count(db_session):
    """One query across all campaigns' confirmations, regardless of how many
    campaigns there are (instead of the old one-query-per-campaign
    `get_campaign_summary()` approach)."""
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    assert len(suggestions) >= 9

    for m in suggestions[:9]:
        create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=[m.member_id], deadline_days=7)

    # Re-fetch via the same helper the router actually uses, exactly like
    # `list_renewal_campaigns_route` does — each `create_renewal_campaign()`
    # call above commits, which (with SQLAlchemy's default
    # `expire_on_commit`) expires every previously-created campaign object in
    # the session; re-querying avoids that test-only artifact and matches
    # real request-scoped usage, where campaigns are freshly loaded once.
    campaigns = list_campaigns_for_group(db_session, group.id)
    assert len(campaigns) >= 3

    with _count_queries(db_session) as counter:
        get_campaign_summaries(db_session, campaigns)

    assert counter["n"] <= 1
    assert counter["n"] < len(campaigns)


# ---------------------------------------------------------------------------
# HTTP-level tests (auth gating + end-to-end flow through the app)
# ---------------------------------------------------------------------------


def _login(client) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "changeme123"})
    assert response.status_code == 200


def _get_group_id(client, community_id: str, name: str) -> str:
    groups = client.get(f"/api/v1/communities/{community_id}/groups").json()
    return next(g["id"] for g in groups if g["name"] == name)


def test_renewal_routes_require_auth(client):
    fake_id = "00000000-0000-0000-0000-000000000000"

    endpoints = [
        ("get", f"/api/v1/groups/{fake_id}/renewals/suggestions"),
        ("post", f"/api/v1/groups/{fake_id}/renewals"),
        ("get", f"/api/v1/groups/{fake_id}/renewals"),
        ("get", f"/api/v1/renewals/{fake_id}"),
        ("post", f"/api/v1/renewals/{fake_id}/confirmations/{fake_id}/confirm"),
        ("get", f"/api/v1/renewals/{fake_id}/non-responders"),
    ]
    for method, path in endpoints:
        if method == "post":
            response = client.post(path, json={})
        else:
            response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "unauthorized", path


def test_renewal_endpoints_end_to_end_flow(client):
    _login(client)

    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")
    group_id = _get_group_id(client, unity_alpha["id"], "Marketplace")

    suggestions_response = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions")
    assert suggestions_response.status_code == 200
    suggestions = suggestions_response.json()
    assert len(suggestions) > 0
    for row in suggestions:
        assert "activityUnknown" not in row
        assert "lastMessageAt" in row
        assert "lastSeenAt" in row
        # the real provider never supplies presence data (verified live) —
        # the mock provider deliberately mirrors that honesty too.
        assert row["lastSeenAt"] is None

    group_members_response = client.get(f"/api/v1/groups/{group_id}/members").json()
    admin_ids = {m["memberId"] for m in group_members_response if m["isAdmin"] or m["isSuperAdmin"]}
    suggestion_ids = {row["memberId"] for row in suggestions}
    assert suggestion_ids.isdisjoint(admin_ids)

    chosen_ids = [row["memberId"] for row in suggestions[:2]]

    create_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 7},
    )
    assert create_response.status_code == 200
    campaign = create_response.json()
    assert campaign["pendingCount"] == 2
    assert campaign["confirmedCount"] == 0
    assert campaign["expiredCount"] == 0
    campaign_id = campaign["id"]

    # rejecting an admin in the request body
    admin_id = next(iter(admin_ids))
    reject_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": [admin_id], "deadlineDays": 7},
    )
    assert reject_response.status_code == 400
    assert reject_response.json()["error"]["code"] == "bad_request"

    detail_response = client.get(f"/api/v1/renewals/{campaign_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert len(detail["confirmations"]) == 2
    assert {c["status"] for c in detail["confirmations"]} == {"pending"}

    list_response = client.get(f"/api/v1/groups/{group_id}/renewals")
    assert list_response.status_code == 200
    assert any(c["id"] == campaign_id for c in list_response.json())

    confirm_response = client.post(
        f"/api/v1/renewals/{campaign_id}/confirmations/{chosen_ids[0]}/confirm"
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "confirmed"
    assert confirm_response.json()["respondedAt"] is not None

    detail_after = client.get(f"/api/v1/renewals/{campaign_id}").json()
    assert detail_after["confirmedCount"] == 1
    assert detail_after["pendingCount"] == 1

    # confirming an unknown member on a real campaign 404s
    fake_member_id = "00000000-0000-0000-0000-000000000000"
    missing_confirmation = client.post(
        f"/api/v1/renewals/{campaign_id}/confirmations/{fake_member_id}/confirm"
    )
    assert missing_confirmation.status_code == 404

    # confirming on an unknown campaign also 404s
    fake_campaign_id = "00000000-0000-0000-0000-000000000000"
    missing_campaign = client.post(
        f"/api/v1/renewals/{fake_campaign_id}/confirmations/{chosen_ids[0]}/confirm"
    )
    assert missing_campaign.status_code == 404

    non_responders_response = client.get(f"/api/v1/renewals/{campaign_id}/non-responders")
    assert non_responders_response.status_code == 200
    assert non_responders_response.json() == []  # deadline hasn't passed yet


def test_list_campaigns_endpoint_returns_distinct_counts_per_campaign(client):
    """End-to-end version of `test_get_campaign_summaries_matches_per_campaign_summary_for_multiple_campaigns`
    above — confirms the router's batched summary wiring produces correct,
    independent counts per campaign rather than accidentally mixing them up
    or reusing one campaign's counts for another."""
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")
    group_id = _get_group_id(client, unity_alpha["id"], "Marketplace")

    suggestions = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions").json()
    assert len(suggestions) >= 5

    campaign_one = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": [suggestions[0]["memberId"], suggestions[1]["memberId"]], "deadlineDays": 7},
    ).json()
    campaign_two_ids = [suggestions[2]["memberId"], suggestions[3]["memberId"], suggestions[4]["memberId"]]
    campaign_two = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": campaign_two_ids, "deadlineDays": 7},
    ).json()

    # confirm one member of campaign_two only.
    confirm_response = client.post(
        f"/api/v1/renewals/{campaign_two['id']}/confirmations/{campaign_two_ids[0]}/confirm"
    )
    assert confirm_response.status_code == 200

    listing = client.get(f"/api/v1/groups/{group_id}/renewals").json()
    by_id = {c["id"]: c for c in listing}

    assert by_id[campaign_one["id"]]["totalCount"] == 2
    assert by_id[campaign_one["id"]]["pendingCount"] == 2
    assert by_id[campaign_one["id"]]["confirmedCount"] == 0

    assert by_id[campaign_two["id"]]["totalCount"] == 3
    assert by_id[campaign_two["id"]]["confirmedCount"] == 1
    assert by_id[campaign_two["id"]]["pendingCount"] == 2


def test_create_campaign_rejects_out_of_range_deadline_days(client):
    """`deadline_days` has no upper/lower bound beyond `Field(ge=1, le=365)`
    (see `renewals/schemas.py`): a negative value would create an instantly-
    "expired" campaign with no error, and an absurdly large one would
    overflow `now + timedelta(days=...)` in `create_renewal_campaign` with a
    raw `OverflowError` instead of a clean 422. Pydantic's own validation
    should reject both before either code path is ever reached."""
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")
    group_id = _get_group_id(client, unity_alpha["id"], "Marketplace")
    suggestions = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions").json()
    chosen_ids = [row["memberId"] for row in suggestions[:1]]

    negative_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": -1},
    )
    assert negative_response.status_code == 422

    zero_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 0},
    )
    assert zero_response.status_code == 422

    huge_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 10**9},
    )
    assert huge_response.status_code == 422

    # a value at each bound is still accepted.
    ok_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 365},
    )
    assert ok_response.status_code == 200


def test_double_confirming_same_renewal_is_low_risk_and_left_unguarded(client):
    """Documents the current, intentional behavior: there is no idempotency
    guard on `confirm_renewal` today. Confirming an already-confirmed
    renewal is a low-risk, admin-only, manual action (it can only ever move
    `status` from `pending` to `confirmed`, never regress it, and every
    campaign/member combination already has exactly one `RenewalConfirmation`
    row via its own unique constraint) — so this locks in the current
    behavior (still 200, status stays `confirmed`, one extra append-only
    audit event per call) rather than introducing a new guard for a P2 test
    task; if that behavior is ever considered a problem, this test should be
    the first thing updated alongside the fix."""
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")
    group_id = _get_group_id(client, unity_alpha["id"], "Marketplace")
    suggestions = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions").json()
    chosen_ids = [row["memberId"] for row in suggestions[:1]]

    campaign_id = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 7},
    ).json()["id"]

    audit_before = client.get("/api/v1/audit", params={"action": "renewal.confirmed"}).json()
    matching_before = [e for e in audit_before if e["targetId"] == chosen_ids[0]]

    first = client.post(f"/api/v1/renewals/{campaign_id}/confirmations/{chosen_ids[0]}/confirm")
    assert first.status_code == 200
    assert first.json()["status"] == "confirmed"
    first_responded_at = first.json()["respondedAt"]

    second = client.post(f"/api/v1/renewals/{campaign_id}/confirmations/{chosen_ids[0]}/confirm")
    assert second.status_code == 200
    assert second.json()["status"] == "confirmed"
    # current behavior: responded_at is overwritten with a fresh timestamp,
    # not preserved from the first confirmation.
    assert second.json()["respondedAt"] >= first_responded_at

    audit_after = client.get("/api/v1/audit", params={"action": "renewal.confirmed"}).json()
    matching_after = [e for e in audit_after if e["targetId"] == chosen_ids[0]]
    # one audit event per confirm call, on top of whatever this member id
    # already had from other tests sharing the same session-scoped DB — no
    # dedup today.
    assert len(matching_after) == len(matching_before) + 2


def test_renewal_campaign_404_for_unknown_ids(client):
    _login(client)
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/renewals/{fake_id}").status_code == 404
    assert client.get(f"/api/v1/renewals/{fake_id}/non-responders").status_code == 404
    assert client.get(f"/api/v1/groups/{fake_id}/renewals/suggestions").status_code == 404
    assert client.get(f"/api/v1/groups/{fake_id}/renewals").status_code == 404


def _seed_viewer_user() -> None:
    """Creates a `viewer`-role user directly via the DB, bypassing the
    normal (owner-only, not yet built) user-management flow — same pattern
    used in `test_moderation.py`."""
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


def test_viewer_role_gets_403_on_create_and_confirm_but_owner_gets_200(client):
    _seed_viewer_user()

    # set up a campaign as owner first (creating one is itself gated).
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")
    group_id = _get_group_id(client, unity_alpha["id"], "Marketplace")

    suggestions = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions").json()
    chosen_ids = [row["memberId"] for row in suggestions[:2]]

    create_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 7},
    )
    assert create_response.status_code == 200
    campaign_id = create_response.json()["id"]
    client.post("/api/v1/auth/logout")

    viewer_login = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-123"})
    assert viewer_login.status_code == 200
    assert viewer_login.json()["role"] == "viewer"

    viewer_create_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 7},
    )
    assert viewer_create_response.status_code == 403
    assert viewer_create_response.json()["error"]["code"] == "forbidden"

    viewer_confirm_response = client.post(
        f"/api/v1/renewals/{campaign_id}/confirmations/{chosen_ids[0]}/confirm"
    )
    assert viewer_confirm_response.status_code == 403
    assert viewer_confirm_response.json()["error"]["code"] == "forbidden"

    client.post("/api/v1/auth/logout")
    _login(client)

    assert (
        client.post(f"/api/v1/renewals/{campaign_id}/confirmations/{chosen_ids[0]}/confirm").status_code
        == 200
    )


# ---------------------------------------------------------------------------
# automated reminder sending + ❌-decline
# ---------------------------------------------------------------------------


class _FailingSendProvider(MockWhatsAppProvider):
    """Same fixture data, but `send_text_message` always raises — used to
    confirm a send failure never blocks campaign creation."""

    def send_text_message(self, member_wa_id: str, message: str) -> str | None:
        raise WhatsAppProviderUnavailableError("boom")


class _FailingRemoveProvider(MockWhatsAppProvider):
    """Same fixture data, but `remove_member` always raises — used to confirm
    a provider failure for one member never blocks `process_due_removals`
    from processing the rest of the batch."""

    def remove_member(self, group_wa_id: str, member_wa_id: str) -> None:
        raise WhatsAppProviderUnavailableError("boom")


def test_build_renewal_reminder_message_contains_both_languages_and_deadline():
    deadline = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    message = build_renewal_reminder_message("Marketplace", deadline)

    assert "Marketplace" in message
    assert "07.09.2026" in message
    assert "❌" in message
    # German first, then English — a rough but real signal both halves exist.
    assert message.index("Hallo!") < message.index("Hi!")


def test_create_renewal_campaign_sends_reminder_to_every_confirmation(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:3]]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)

    confirmations = list(
        db_session.execute(select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)).scalars()
    )
    assert len(confirmations) == 3
    for confirmation in confirmations:
        assert confirmation.reminder_sent_at is not None
        assert confirmation.reminder_message_id is not None


def test_create_renewal_campaign_survives_a_send_failure_for_one_member(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:2]]

    campaign = create_renewal_campaign(db_session, _FailingSendProvider(), group, member_ids=chosen, deadline_days=7)

    confirmations = list(
        db_session.execute(select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)).scalars()
    )
    assert len(confirmations) == 2  # the campaign + both confirmations still exist
    for confirmation in confirmations:
        assert confirmation.reminder_sent_at is None
        assert confirmation.reminder_message_id is None


def test_send_renewal_reminder_resends_and_updates_timestamp(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [suggestions[0].member_id]

    campaign = create_renewal_campaign(db_session, _FailingSendProvider(), group, member_ids=chosen, deadline_days=7)
    confirmation = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalar_one()
    assert confirmation.reminder_sent_at is None  # the initial send failed

    updated = send_renewal_reminder(db_session, MockWhatsAppProvider(), confirmation, campaign)

    assert updated.reminder_sent_at is not None
    assert updated.reminder_message_id is not None


def test_send_renewal_reminder_rejects_already_confirmed(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [suggestions[0].member_id]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)
    confirmation = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalar_one()
    confirm_renewal(db_session, confirmation)

    try:
        send_renewal_reminder(db_session, MockWhatsAppProvider(), confirmation, campaign)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 409


def test_apply_renewal_decline_reaction_sets_declined_at_and_is_idempotent_noop_for_unknown_id(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [suggestions[0].member_id]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)
    confirmation = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalar_one()
    message_id = confirmation.reminder_message_id
    assert message_id is not None

    assert apply_renewal_decline_reaction(db_session, "no-such-message-id") is False

    assert apply_renewal_decline_reaction(db_session, message_id) is True
    db_session.refresh(confirmation)
    assert confirmation.declined_at is not None
    assert confirmation.status == RenewalConfirmationStatus.pending


def test_is_confirmation_expired_true_immediately_on_decline_even_before_deadline(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [suggestions[0].member_id]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=30)
    confirmation = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalar_one()

    assert is_confirmation_expired(confirmation, campaign) is False  # deadline weeks away, not declined

    apply_renewal_decline_reaction(db_session, confirmation.reminder_message_id)
    db_session.refresh(confirmation)

    assert is_confirmation_expired(confirmation, campaign) is True


def test_apply_renewal_confirm_reaction_confirms_and_un_declines(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [suggestions[0].member_id]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)
    confirmation = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalar_one()
    message_id = confirmation.reminder_message_id

    # changed their mind: declined first, then reacted 👍 — should un-decline
    # and confirm, not be ignored.
    apply_renewal_decline_reaction(db_session, message_id)
    db_session.refresh(confirmation)
    assert confirmation.declined_at is not None

    assert apply_renewal_confirm_reaction(db_session, "no-such-message-id") is False
    assert apply_renewal_confirm_reaction(db_session, message_id) is True

    db_session.refresh(confirmation)
    assert confirmation.status == RenewalConfirmationStatus.confirmed
    assert confirmation.responded_at is not None
    assert confirmation.declined_at is None
    assert is_confirmation_expired(confirmation, campaign) is False


def test_apply_renewal_confirm_reaction_is_noop_once_already_confirmed(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [suggestions[0].member_id]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)
    confirmation = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalar_one()
    message_id = confirmation.reminder_message_id

    confirm_renewal(db_session, confirmation)
    db_session.refresh(confirmation)
    first_responded_at = confirmation.responded_at

    # a later ❌ on an already-confirmed message must not un-confirm them.
    assert apply_renewal_decline_reaction(db_session, message_id) is False
    db_session.refresh(confirmation)
    assert confirmation.status == RenewalConfirmationStatus.confirmed
    assert confirmation.declined_at is None
    assert confirmation.responded_at == first_responded_at


def test_remove_from_campaign_deletes_row_and_writes_audit_event(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:2]]

    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)
    confirmation = db_session.execute(
        select(RenewalConfirmation).where(
            RenewalConfirmation.campaign_id == campaign.id, RenewalConfirmation.member_id == chosen[0]
        )
    ).scalar_one()

    remove_from_campaign(db_session, confirmation)

    remaining = list(
        db_session.execute(select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)).scalars()
    )
    assert {c.member_id for c in remaining} == {chosen[1]}

    audit_events = db_session.execute(select(AuditEvent)).scalars().all()
    removed_event = next(e for e in audit_events if e.action == "renewal.removed_from_campaign")
    assert removed_event.target_id == str(chosen[0])
    assert removed_event.detail["campaignId"] == str(campaign.id)


def test_delete_campaign_requires_archiving_first(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:1]]
    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)

    try:
        delete_campaign(db_session, campaign)
        raise AssertionError("expected a conflict")
    except ApiError as exc:
        assert exc.status_code == 409

    campaign = archive_campaign(db_session, campaign)
    assert campaign.archived_at is not None

    delete_campaign(db_session, campaign)
    assert db_session.get(type(campaign), campaign.id) is None

    audit_events = db_session.execute(select(AuditEvent)).scalars().all()
    assert any(e.action == "renewal.campaign_archived" for e in audit_events)
    assert any(e.action == "renewal.campaign_deleted" for e in audit_events)


def test_archive_and_unarchive_are_not_re_entrant(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:1]]
    campaign = create_renewal_campaign(db_session, MockWhatsAppProvider(), group, member_ids=chosen, deadline_days=7)

    archive_campaign(db_session, campaign)
    try:
        archive_campaign(db_session, campaign)
        raise AssertionError("expected a conflict")
    except ApiError as exc:
        assert exc.status_code == 409

    unarchive_campaign(db_session, campaign)
    try:
        unarchive_campaign(db_session, campaign)
        raise AssertionError("expected a conflict")
    except ApiError as exc:
        assert exc.status_code == 409


def test_check_renewal_reactions_applies_simulated_reactions_and_returns_count(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:3]]

    provider = MockWhatsAppProvider()
    campaign = create_renewal_campaign(db_session, provider, group, member_ids=chosen, deadline_days=7)
    confirmations = list(
        db_session.execute(select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)).scalars()
    )
    assert len(confirmations) == 3

    # member 0 reacted 👍, member 1 reacted ❌, member 2 did nothing yet.
    provider.simulate_reaction(confirmations[0].reminder_message_id, "👍")
    provider.simulate_reaction(confirmations[1].reminder_message_id, "❌")

    updated_count = check_renewal_reactions(db_session, provider, campaign)
    assert updated_count == 2

    db_session.refresh(confirmations[0])
    db_session.refresh(confirmations[1])
    db_session.refresh(confirmations[2])
    assert confirmations[0].status == RenewalConfirmationStatus.confirmed
    assert confirmations[1].declined_at is not None
    assert confirmations[2].status == RenewalConfirmationStatus.pending
    assert confirmations[2].declined_at is None

    # running it again with no new reactions must be a safe no-op (already
    # non-pending confirmations are excluded from the pull query).
    assert check_renewal_reactions(db_session, provider, campaign) == 0


# ---------------------------------------------------------------------------
# process_due_removals
# ---------------------------------------------------------------------------


def test_process_due_removals_removes_declined_and_expired_but_not_in_window_pending(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:3]]

    provider = MockWhatsAppProvider()
    campaign = create_renewal_campaign(db_session, provider, group, member_ids=chosen, deadline_days=30)
    confirmations = {
        c.member_id: c
        for c in db_session.execute(
            select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
        ).scalars()
    }

    # member 0: declined (immediately due, regardless of the far-off deadline).
    apply_renewal_decline_reaction(db_session, confirmations[chosen[0]].reminder_message_id)
    # member 1: left pending, deadline still weeks away — not due.
    # member 2: also left pending, but we push the *campaign* deadline into
    # the past for this assertion instead — see below.

    removed = process_due_removals(db_session, provider, campaign)
    assert removed == 1

    db_session.refresh(confirmations[chosen[0]])
    db_session.refresh(confirmations[chosen[1]])
    assert confirmations[chosen[0]].removed_at is not None
    assert confirmations[chosen[1]].removed_at is None

    remaining_group_member_ids = {
        m.member_id
        for m in db_session.execute(
            select(GroupMembership).where(GroupMembership.group_id == group.id)
        ).scalars()
    }
    assert chosen[0] not in remaining_group_member_ids
    assert chosen[1] in remaining_group_member_ids

    audit_events = db_session.execute(select(AuditEvent)).scalars().all()
    removed_event = next(e for e in audit_events if e.action == "renewal.member_removed")
    assert removed_event.target_id == str(chosen[0])
    assert removed_event.detail["campaignId"] == str(campaign.id)
    assert any(e.action == "group.member.removed" for e in audit_events)


def test_process_due_removals_is_idempotent_on_repeat_calls(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [suggestions[0].member_id]

    provider = MockWhatsAppProvider()
    campaign = create_renewal_campaign(db_session, provider, group, member_ids=chosen, deadline_days=30)
    confirmation = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalar_one()
    apply_renewal_decline_reaction(db_session, confirmation.reminder_message_id)

    assert process_due_removals(db_session, provider, campaign) == 1
    # a second call must not try to remove the same (already-gone) member
    # again — no provider call, no re-count.
    assert process_due_removals(db_session, provider, campaign) == 0


def test_process_due_removals_survives_a_provider_failure_for_one_member(db_session):
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [m.member_id for m in suggestions[:2]]

    provider = _FailingRemoveProvider()
    campaign = create_renewal_campaign(db_session, provider, group, member_ids=chosen, deadline_days=30)
    confirmations = {
        c.member_id: c
        for c in db_session.execute(
            select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
        ).scalars()
    }
    apply_renewal_decline_reaction(db_session, confirmations[chosen[0]].reminder_message_id)
    apply_renewal_decline_reaction(db_session, confirmations[chosen[1]].reminder_message_id)

    # both are due, but every provider call fails — nobody actually gets
    # removed, and the batch doesn't blow up.
    assert process_due_removals(db_session, provider, campaign) == 0

    db_session.refresh(confirmations[chosen[0]])
    db_session.refresh(confirmations[chosen[1]])
    assert confirmations[chosen[0]].removed_at is None
    assert confirmations[chosen[1]].removed_at is None


def test_process_due_removals_treats_an_already_gone_membership_as_done(db_session):
    """If the member was already removed from the group some other way (e.g.
    manually via the Members tab), `process_due_removals` must not 404 —
    it just marks the confirmation as removed without another provider
    call."""
    group = _sync_unity_marketplace(db_session)
    suggestions = get_renewal_suggestions(db_session, group)
    chosen = [suggestions[0].member_id]

    provider = MockWhatsAppProvider()
    campaign = create_renewal_campaign(db_session, provider, group, member_ids=chosen, deadline_days=30)
    confirmation = db_session.execute(
        select(RenewalConfirmation).where(RenewalConfirmation.campaign_id == campaign.id)
    ).scalar_one()
    apply_renewal_decline_reaction(db_session, confirmation.reminder_message_id)

    # remove the underlying membership directly, bypassing this module.
    membership = db_session.execute(
        select(GroupMembership).where(
            GroupMembership.group_id == group.id, GroupMembership.member_id == chosen[0]
        )
    ).scalar_one()
    db_session.delete(membership)
    db_session.commit()

    assert process_due_removals(db_session, provider, campaign) == 1
    db_session.refresh(confirmation)
    assert confirmation.removed_at is not None


# ---------------------------------------------------------------------------
# HTTP-level: remove / check-reactions / process-removals
# ---------------------------------------------------------------------------


def test_remove_from_campaign_route_returns_204_and_drops_the_member(client):
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity = next(c for c in communities if c["name"] == "Unity Alpha")
    group_id = _get_group_id(client, unity["id"], "Marketplace")
    suggestions = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions").json()
    member_id = suggestions[0]["memberId"]

    create_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": [member_id], "deadlineDays": 7},
    )
    campaign_id = create_response.json()["id"]

    remove_response = client.post(f"/api/v1/renewals/{campaign_id}/confirmations/{member_id}/remove")
    assert remove_response.status_code == 204

    detail = client.get(f"/api/v1/renewals/{campaign_id}").json()
    assert detail["confirmations"] == []
    assert detail["totalCount"] == 0


def test_check_reactions_route_returns_updated_detail(client):
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity = next(c for c in communities if c["name"] == "Unity Alpha")
    group_id = _get_group_id(client, unity["id"], "Marketplace")
    suggestions = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions").json()
    member_id = suggestions[1]["memberId"]

    create_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": [member_id], "deadlineDays": 7},
    )
    campaign_id = create_response.json()["id"]

    # No real reaction exists yet (mock provider, nothing simulated) — the
    # endpoint must still succeed and report the campaign unchanged.
    response = client.post(f"/api/v1/renewals/{campaign_id}/check-reactions")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == campaign_id
    assert body["confirmations"][0]["memberId"] == member_id
    assert body["confirmations"][0]["status"] == "pending"


def test_archive_unarchive_delete_route_flow(client):
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity = next(c for c in communities if c["name"] == "Unity Alpha")
    group_id = _get_group_id(client, unity["id"], "Marketplace")
    suggestions = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions").json()
    member_id = suggestions[0]["memberId"]

    create_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": [member_id], "deadlineDays": 7},
    )
    campaign_id = create_response.json()["id"]

    # Deleting before archiving is refused.
    premature_delete = client.delete(f"/api/v1/renewals/{campaign_id}")
    assert premature_delete.status_code == 409

    archive_response = client.post(f"/api/v1/renewals/{campaign_id}/archive")
    assert archive_response.status_code == 200
    assert archive_response.json()["archivedAt"] is not None

    unarchive_response = client.post(f"/api/v1/renewals/{campaign_id}/unarchive")
    assert unarchive_response.status_code == 200
    assert unarchive_response.json()["archivedAt"] is None

    client.post(f"/api/v1/renewals/{campaign_id}/archive")
    delete_response = client.delete(f"/api/v1/renewals/{campaign_id}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/renewals/{campaign_id}").status_code == 404


def test_process_removals_route_removes_declined_member_from_group(client):
    """Uses Riverside Collective's Volunteers group (not Unity
    Alpha/Marketplace) — this test causes a *real* provider-level removal
    against the `client` fixture's session-scoped shared provider instance,
    which would otherwise permanently mutate Marketplace's member count for
    every other HTTP-level test sharing that same app/provider for the rest
    of the test session (the exact cross-test pollution gotcha this suite
    already works around elsewhere for mutating Marketplace via join-request
    approval)."""
    _login(client)
    communities = client.get("/api/v1/communities").json()
    riverside = next(c for c in communities if c["name"] == "Riverside Collective")
    group_id = _get_group_id(client, riverside["id"], "Volunteers")
    suggestions = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions").json()
    member_id = suggestions[0]["memberId"]

    create_response = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": [member_id], "deadlineDays": 30},
    )
    campaign_id = create_response.json()["id"]

    before_members = client.get(f"/api/v1/groups/{group_id}/members").json()
    assert any(m["memberId"] == member_id for m in before_members)

    # `RenewalConfirmationOut` never exposes `reminder_message_id` over HTTP
    # (it's purely an internal correlation id), so fetch it directly from the
    # DB — same direct-DB-access pattern `_seed_viewer_user` above already
    # uses for HTTP-level test setup — and simulate the ❌ reaction through
    # the shared provider instance (the same `lru_cache`d singleton
    # `get_provider()` hands the app), then let "check reactions" apply it,
    # mirroring the exact pull-based path the frontend uses.
    import uuid as uuid_module

    from communeer.db import SessionLocal
    from communeer.providers.whatsapp import get_provider as get_shared_provider

    db = SessionLocal()
    try:
        reminder_message_id = db.execute(
            select(RenewalConfirmation.reminder_message_id).where(
                RenewalConfirmation.campaign_id == uuid_module.UUID(campaign_id),
                RenewalConfirmation.member_id == uuid_module.UUID(member_id),
            )
        ).scalar_one()
    finally:
        db.close()

    provider = get_shared_provider()
    provider.simulate_reaction(reminder_message_id, "❌")

    check_response = client.post(f"/api/v1/renewals/{campaign_id}/check-reactions")
    assert check_response.status_code == 200
    assert check_response.json()["confirmations"][0]["declinedAt"] is not None

    process_response = client.post(f"/api/v1/renewals/{campaign_id}/process-removals")
    assert process_response.status_code == 200
    body = process_response.json()
    assert body["confirmations"][0]["removedAt"] is not None

    after_members = client.get(f"/api/v1/groups/{group_id}/members").json()
    assert not any(m["memberId"] == member_id for m in after_members)


def test_process_removals_route_requires_manager_role(client):
    _seed_viewer_user()
    _login(client)
    communities = client.get("/api/v1/communities").json()
    unity = next(c for c in communities if c["name"] == "Unity Alpha")
    group_id = _get_group_id(client, unity["id"], "Marketplace")
    suggestions = client.get(f"/api/v1/groups/{group_id}/renewals/suggestions").json()
    member_id = suggestions[0]["memberId"]

    campaign_id = client.post(
        f"/api/v1/groups/{group_id}/renewals",
        json={"memberIds": [member_id], "deadlineDays": 7},
    ).json()["id"]
    client.post("/api/v1/auth/logout")

    client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-123"})
    viewer_response = client.post(f"/api/v1/renewals/{campaign_id}/process-removals")
    assert viewer_response.status_code == 403

    client.post("/api/v1/auth/logout")
    _login(client)
    owner_response = client.post(f"/api/v1/renewals/{campaign_id}/process-removals")
    assert owner_response.status_code == 200
