from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from communeer.models import AuditEvent, Community
from communeer.models.renewal import (
    RenewalConfirmation,
    RenewalConfirmationStatus,
)
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.renewals.service import (
    confirm_renewal,
    create_renewal_campaign,
    get_campaign_summary,
    get_non_responders,
    get_renewal_suggestions,
)
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"


def _sync_unity(db_session) -> Community:
    provider = MockWhatsAppProvider()
    community = sync_community(db_session, provider, UNITY_WA_ID)
    return community


def test_suggestions_never_include_an_admin(db_session):
    community = _sync_unity(db_session)

    suggestions = get_renewal_suggestions(db_session, community)

    assert len(suggestions) > 0
    for agg in suggestions:
        assert not agg.is_admin
        assert not agg.is_community_admin


def test_suggestions_sorted_oldest_joined_first_with_none_last(db_session):
    community = _sync_unity(db_session)

    suggestions = get_renewal_suggestions(db_session, community)

    joined_ats = [a.joined_at for a in suggestions]
    non_none = [j for j in joined_ats if j is not None]
    assert non_none == sorted(non_none)
    # every None (if any) must trail every non-None value
    first_none_index = next((i for i, j in enumerate(joined_ats) if j is None), None)
    if first_none_index is not None:
        assert all(j is None for j in joined_ats[first_none_index:])


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
        assert row["activityUnknown"] is True

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


def test_renewal_campaign_404_for_unknown_ids(client):
    _login(client)
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/renewals/{fake_id}").status_code == 404
    assert client.get(f"/api/v1/renewals/{fake_id}/non-responders").status_code == 404
    assert client.get(f"/api/v1/communities/{fake_id}/renewals/suggestions").status_code == 404
    assert client.get(f"/api/v1/communities/{fake_id}/renewals").status_code == 404
