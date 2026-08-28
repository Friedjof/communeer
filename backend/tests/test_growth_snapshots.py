from sqlalchemy import select

from communeer.communities.service import (
    get_community_admin_count,
    get_community_pending_request_count,
)
from communeer.models import CommunityMemberSnapshot, Group, GroupMemberSnapshot
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"


def test_two_syncs_produce_two_undeduplicated_snapshot_rows(db_session):
    """The whole point of the snapshot tables is a time series: repeated
    syncs must add rows, never overwrite/dedupe an existing one."""
    provider = MockWhatsAppProvider()

    community = sync_community(db_session, provider, UNITY_WA_ID)
    groups = {g.name: g for g in db_session.execute(select(Group)).scalars()}

    community_snapshots_after_first = db_session.execute(
        select(CommunityMemberSnapshot).where(CommunityMemberSnapshot.community_id == community.id)
    ).scalars().all()
    assert len(community_snapshots_after_first) == 1

    group_snapshots_after_first = db_session.execute(
        select(GroupMemberSnapshot).where(GroupMemberSnapshot.group_id == groups["Marketplace"].id)
    ).scalars().all()
    assert len(group_snapshots_after_first) == 1

    sync_community(db_session, provider, UNITY_WA_ID)

    community_snapshots = db_session.execute(
        select(CommunityMemberSnapshot)
        .where(CommunityMemberSnapshot.community_id == community.id)
        .order_by(CommunityMemberSnapshot.recorded_at.asc())
    ).scalars().all()
    assert len(community_snapshots) == 2
    assert community_snapshots[0].recorded_at < community_snapshots[1].recorded_at

    for group_name in ("Marketplace", "General", "Events", "Announcements"):
        group_snapshots = db_session.execute(
            select(GroupMemberSnapshot)
            .where(GroupMemberSnapshot.group_id == groups[group_name].id)
            .order_by(GroupMemberSnapshot.recorded_at.asc())
        ).scalars().all()
        assert len(group_snapshots) == 2, group_name
        assert group_snapshots[0].recorded_at < group_snapshots[1].recorded_at, group_name


def test_snapshot_values_match_recomputed_counts_at_sync_time(db_session):
    provider = MockWhatsAppProvider()

    community = sync_community(db_session, provider, UNITY_WA_ID)
    groups = {g.name: g for g in db_session.execute(select(Group)).scalars()}

    community_snapshot = db_session.execute(
        select(CommunityMemberSnapshot).where(CommunityMemberSnapshot.community_id == community.id)
    ).scalar_one()
    assert community_snapshot.member_count == community.member_count
    assert community_snapshot.group_count == community.group_count
    assert community_snapshot.admin_count == get_community_admin_count(db_session, community.id)
    assert community_snapshot.pending_request_count == get_community_pending_request_count(db_session, community.id)

    marketplace = groups["Marketplace"]
    marketplace_snapshot = db_session.execute(
        select(GroupMemberSnapshot).where(GroupMemberSnapshot.group_id == marketplace.id)
    ).scalar_one()
    assert marketplace_snapshot.member_count == marketplace.member_count == 981
    assert marketplace_snapshot.pending_request_count == marketplace.pending_request_count == 3

    # a second sync (mock data is static, so counts don't move) must still
    # write a *second*, independent row with matching values — not update
    # the first one in place.
    sync_community(db_session, provider, UNITY_WA_ID)
    db_session.expire_all()

    marketplace_snapshots = db_session.execute(
        select(GroupMemberSnapshot)
        .where(GroupMemberSnapshot.group_id == marketplace.id)
        .order_by(GroupMemberSnapshot.recorded_at.asc())
    ).scalars().all()
    assert len(marketplace_snapshots) == 2
    assert marketplace_snapshots[0].member_count == marketplace_snapshots[1].member_count == 981
    assert marketplace_snapshots[0].pending_request_count == marketplace_snapshots[1].pending_request_count == 3
    assert marketplace_snapshots[0].id != marketplace_snapshots[1].id


def _login(client) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "changeme123"})
    assert response.status_code == 200


def test_community_history_endpoint_requires_auth(client):
    communities = client.get("/api/v1/communities")
    assert communities.status_code == 401
    assert communities.json()["error"]["code"] == "unauthorized"


def test_history_endpoints_reject_unauthenticated_requests(client):
    # router-level auth dependency runs before the path is resolved, so a
    # made-up id is enough to prove the 401 gate applies to these routes too.
    fake_id = "00000000-0000-0000-0000-000000000000"
    history = client.get(f"/api/v1/communities/{fake_id}/history")
    assert history.status_code == 401
    assert history.json()["error"]["code"] == "unauthorized"

    groups_history = client.get(f"/api/v1/communities/{fake_id}/groups/history")
    assert groups_history.status_code == 401
    assert groups_history.json()["error"]["code"] == "unauthorized"


def test_history_endpoints_return_ordered_snapshots(client):
    _login(client)

    communities = client.get("/api/v1/communities").json()
    unity_alpha = next(c for c in communities if c["name"] == "Unity Alpha")
    community_id = unity_alpha["id"]

    # the app's startup lifespan already primes one sync for every provider
    # community, so there's already one data point before we trigger another.
    sync_response = client.post(f"/api/v1/communities/{community_id}/sync")
    assert sync_response.status_code == 200

    history = client.get(f"/api/v1/communities/{community_id}/history")
    assert history.status_code == 200
    points = history.json()
    assert len(points) >= 2

    recorded_ats = [p["recordedAt"] for p in points]
    assert recorded_ats == sorted(recorded_ats)
    for point in points:
        assert set(point.keys()) == {"recordedAt", "memberCount", "groupCount", "adminCount", "pendingRequestCount"}
    assert points[-1]["memberCount"] == unity_alpha["memberCount"]
    assert points[-1]["groupCount"] == unity_alpha["groupCount"]

    groups_history = client.get(f"/api/v1/communities/{community_id}/groups/history")
    assert groups_history.status_code == 200
    series = groups_history.json()
    assert len(series) == unity_alpha["groupCount"]

    marketplace_series = next(s for s in series if s["groupName"] == "Marketplace")
    assert len(marketplace_series["snapshots"]) >= 2
    snapshot_recorded_ats = [s["recordedAt"] for s in marketplace_series["snapshots"]]
    assert snapshot_recorded_ats == sorted(snapshot_recorded_ats)
    assert marketplace_series["snapshots"][-1]["memberCount"] == 981
    assert marketplace_series["snapshots"][-1]["pendingRequestCount"] == 3
    for snap in marketplace_series["snapshots"]:
        assert set(snap.keys()) == {"recordedAt", "memberCount", "pendingRequestCount"}


def test_history_endpoints_404_for_unknown_community(client):
    _login(client)
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/communities/{fake_id}/history").status_code == 404
    assert client.get(f"/api/v1/communities/{fake_id}/groups/history").status_code == 404
