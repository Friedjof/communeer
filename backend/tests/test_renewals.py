from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import event, select

from communeer.models import AuditEvent, Community
from communeer.models.renewal import (
    RenewalConfirmation,
    RenewalConfirmationStatus,
)
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.renewals.service import (
    confirm_renewal,
    create_renewal_campaign,
    get_campaign_summaries,
    get_campaign_summary,
    get_non_responders,
    get_renewal_suggestions,
    list_campaigns_for_community,
)
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"


def _sync_unity(db_session) -> Community:
    provider = MockWhatsAppProvider()
    community = sync_community(db_session, provider, UNITY_WA_ID)
    return community


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
    community = _sync_unity(db_session)

    suggestions = get_renewal_suggestions(db_session, community)

    assert len(suggestions) > 0
    for agg in suggestions:
        assert not agg.is_admin
        assert not agg.is_community_admin


def test_suggestions_sort_never_posted_members_first_then_oldest_last_message(db_session):
    """Members who have never posted (`last_message_at is None`) are the
    most likely renewal candidates and must surface first, ahead of members
    who have posted at some point — even a long time ago."""
    community = _sync_unity(db_session)

    suggestions = get_renewal_suggestions(db_session, community)
    assert len(suggestions) > 0

    never_posted_flags = [a.last_message_at is None for a in suggestions]
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
    posted_last_message_ats = [a.last_message_at for a in suggestions if a.last_message_at is not None]
    assert posted_last_message_ats == sorted(posted_last_message_ats)


def test_creating_campaign_with_admin_member_is_rejected(db_session):
    community = _sync_unity(db_session)
    aggregates = get_renewal_suggestions(db_session, community)
    non_admin_ids = {a.member.id for a in aggregates}

    from communeer.communities.service import list_community_members

    all_aggregates = list_community_members(db_session, community)
    admin_agg = next(a for a in all_aggregates if a.member.id not in non_admin_ids)
    assert admin_agg.is_admin or admin_agg.is_community_admin

    from communeer.errors import ApiError

    try:
        create_renewal_campaign(db_session, community, member_ids=[admin_agg.member.id], deadline_days=7)
        raised = False
    except ApiError as exc:
        raised = True
        assert exc.status_code == 400
        assert exc.code == "bad_request"

    assert raised


def test_creating_campaign_with_valid_members_creates_pending_confirmations_and_audit_event(db_session):
    community = _sync_unity(db_session)
    suggestions = get_renewal_suggestions(db_session, community)
    chosen = [a.member.id for a in suggestions[:3]]

    audit_count_before = db_session.execute(select(AuditEvent)).scalars().all()

    campaign = create_renewal_campaign(db_session, community, member_ids=chosen, deadline_days=7)

    assert campaign.community_id == community.id
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
    assert new_event.target_type == "community"
    assert new_event.target_id == str(community.id)
    assert new_event.detail["memberCount"] == len(chosen)
    assert new_event.detail["campaignId"] == str(campaign.id)


def test_confirming_flips_status_and_updates_campaign_counts(db_session):
    community = _sync_unity(db_session)
    suggestions = get_renewal_suggestions(db_session, community)
    chosen = [a.member.id for a in suggestions[:4]]

    campaign = create_renewal_campaign(db_session, community, member_ids=chosen, deadline_days=7)

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
    community = _sync_unity(db_session)
    suggestions = get_renewal_suggestions(db_session, community)
    chosen = [a.member.id for a in suggestions[:2]]

    campaign = create_renewal_campaign(db_session, community, member_ids=chosen, deadline_days=7)

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
    community = _sync_unity(db_session)
    suggestions = get_renewal_suggestions(db_session, community)
    chosen = [a.member.id for a in suggestions[:2]]

    campaign = create_renewal_campaign(db_session, community, member_ids=chosen, deadline_days=7)

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
    community = _sync_unity(db_session)
    suggestions = get_renewal_suggestions(db_session, community)
    assert len(suggestions) >= 6

    campaign_a = create_renewal_campaign(
        db_session, community, member_ids=[a.member.id for a in suggestions[:3]], deadline_days=7
    )
    campaign_b = create_renewal_campaign(
        db_session, community, member_ids=[a.member.id for a in suggestions[3:6]], deadline_days=7
    )

    # confirm one member of campaign_b, and expire campaign_a entirely, so the
    # two campaigns end up with genuinely different pending/confirmed/expired
    # splits (not just two copies of the same all-pending counts).
    confirmation_b = db_session.execute(
        select(RenewalConfirmation).where(
            RenewalConfirmation.campaign_id == campaign_b.id,
            RenewalConfirmation.member_id == suggestions[3].member.id,
        )
    ).scalar_one()
    confirm_renewal(db_session, confirmation_b)

    campaign_a.deadline = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    db_session.refresh(campaign_a)
    db_session.refresh(campaign_b)

    campaigns = list_campaigns_for_community(db_session, community.id)
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
    community = _sync_unity(db_session)
    suggestions = get_renewal_suggestions(db_session, community)
    campaign = create_renewal_campaign(db_session, community, member_ids=[suggestions[0].member.id], deadline_days=7)

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
    community = _sync_unity(db_session)
    suggestions = get_renewal_suggestions(db_session, community)
    assert len(suggestions) >= 9

    for a in suggestions[:9]:
        create_renewal_campaign(db_session, community, member_ids=[a.member.id], deadline_days=7)

    # Re-fetch via the same helper the router actually uses, exactly like
    # `list_renewal_campaigns_route` does — each `create_renewal_campaign()`
    # call above commits, which (with SQLAlchemy's default
    # `expire_on_commit`) expires every previously-created campaign object in
    # the session; re-querying avoids that test-only artifact and matches
    # real request-scoped usage, where campaigns are freshly loaded once.
    campaigns = list_campaigns_for_community(db_session, community.id)
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


def test_renewal_routes_require_auth(client):
    fake_id = "00000000-0000-0000-0000-000000000000"

    endpoints = [
        ("get", f"/api/v1/communities/{fake_id}/renewals/suggestions"),
        ("post", f"/api/v1/communities/{fake_id}/renewals"),
        ("get", f"/api/v1/communities/{fake_id}/renewals"),
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
    community_id = unity_alpha["id"]

    suggestions_response = client.get(f"/api/v1/communities/{community_id}/renewals/suggestions")
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

    members_response = client.get(f"/api/v1/communities/{community_id}/members").json()
    admin_ids = {m["id"] for m in members_response if m["isAdmin"] or m["isCommunityAdmin"]}
    suggestion_ids = {row["memberId"] for row in suggestions}
    assert suggestion_ids.isdisjoint(admin_ids)

    chosen_ids = [row["memberId"] for row in suggestions[:2]]

    create_response = client.post(
        f"/api/v1/communities/{community_id}/renewals",
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
        f"/api/v1/communities/{community_id}/renewals",
        json={"memberIds": [admin_id], "deadlineDays": 7},
    )
    assert reject_response.status_code == 400
    assert reject_response.json()["error"]["code"] == "bad_request"

    detail_response = client.get(f"/api/v1/renewals/{campaign_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert len(detail["confirmations"]) == 2
    assert {c["status"] for c in detail["confirmations"]} == {"pending"}

    list_response = client.get(f"/api/v1/communities/{community_id}/renewals")
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
    community_id = unity_alpha["id"]

    suggestions = client.get(f"/api/v1/communities/{community_id}/renewals/suggestions").json()
    assert len(suggestions) >= 5

    campaign_one = client.post(
        f"/api/v1/communities/{community_id}/renewals",
        json={"memberIds": [suggestions[0]["memberId"], suggestions[1]["memberId"]], "deadlineDays": 7},
    ).json()
    campaign_two_ids = [suggestions[2]["memberId"], suggestions[3]["memberId"], suggestions[4]["memberId"]]
    campaign_two = client.post(
        f"/api/v1/communities/{community_id}/renewals",
        json={"memberIds": campaign_two_ids, "deadlineDays": 7},
    ).json()

    # confirm one member of campaign_two only.
    confirm_response = client.post(
        f"/api/v1/renewals/{campaign_two['id']}/confirmations/{campaign_two_ids[0]}/confirm"
    )
    assert confirm_response.status_code == 200

    listing = client.get(f"/api/v1/communities/{community_id}/renewals").json()
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
    community_id = unity_alpha["id"]
    suggestions = client.get(f"/api/v1/communities/{community_id}/renewals/suggestions").json()
    chosen_ids = [row["memberId"] for row in suggestions[:1]]

    negative_response = client.post(
        f"/api/v1/communities/{community_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": -1},
    )
    assert negative_response.status_code == 422

    zero_response = client.post(
        f"/api/v1/communities/{community_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 0},
    )
    assert zero_response.status_code == 422

    huge_response = client.post(
        f"/api/v1/communities/{community_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 10**9},
    )
    assert huge_response.status_code == 422

    # a value at each bound is still accepted.
    ok_response = client.post(
        f"/api/v1/communities/{community_id}/renewals",
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
    community_id = unity_alpha["id"]
    suggestions = client.get(f"/api/v1/communities/{community_id}/renewals/suggestions").json()
    chosen_ids = [row["memberId"] for row in suggestions[:1]]

    campaign_id = client.post(
        f"/api/v1/communities/{community_id}/renewals",
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
    assert client.get(f"/api/v1/communities/{fake_id}/renewals/suggestions").status_code == 404
    assert client.get(f"/api/v1/communities/{fake_id}/renewals").status_code == 404


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
    community_id = unity_alpha["id"]

    suggestions = client.get(f"/api/v1/communities/{community_id}/renewals/suggestions").json()
    chosen_ids = [row["memberId"] for row in suggestions[:2]]

    create_response = client.post(
        f"/api/v1/communities/{community_id}/renewals",
        json={"memberIds": chosen_ids, "deadlineDays": 7},
    )
    assert create_response.status_code == 200
    campaign_id = create_response.json()["id"]
    client.post("/api/v1/auth/logout")

    viewer_login = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-123"})
    assert viewer_login.status_code == 200
    assert viewer_login.json()["role"] == "viewer"

    viewer_create_response = client.post(
        f"/api/v1/communities/{community_id}/renewals",
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
