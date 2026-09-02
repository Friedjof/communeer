from contextlib import contextmanager

from sqlalchemy import event, select

from communeer.communities.service import (
    get_community_admin_count,
    get_community_pending_request_count,
    get_group_admin_count,
    get_group_history_for_community,
    get_group_last_message_at,
)
from communeer.models import (
    CommunityMemberSnapshot,
    Group,
    GroupMembership,
    GroupMemberSnapshot,
)
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.sync.service import sync_community
from tests.conftest import login_as_admin as _login

UNITY_WA_ID = "120363010000000001@g.us"


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


def test_group_admin_count_and_last_message_at_scoped_per_group(db_session):
    """`get_group_admin_count`/`get_group_last_message_at` must aggregate only
    over the one group's own memberships, not bleed in another group's rows —
    the same "scoped, not community-wide" property `get_community_admin_count`
    guards against at the community level."""
    provider = MockWhatsAppProvider()
    sync_community(db_session, provider, UNITY_WA_ID)
    groups = {g.name: g for g in db_session.execute(select(Group)).scalars()}
    marketplace = groups["Marketplace"]
    general = groups["General"]

    marketplace_memberships = db_session.execute(
        select(GroupMembership).where(GroupMembership.group_id == marketplace.id)
    ).scalars().all()
    expected_admin_count = sum(1 for m in marketplace_memberships if m.is_admin)
    expected_last_message_at = max(
        (m.last_message_at for m in marketplace_memberships if m.last_message_at is not None),
        default=None,
    )

    assert get_group_admin_count(db_session, marketplace.id) == expected_admin_count
    assert get_group_last_message_at(db_session, marketplace.id) == expected_last_message_at

    # scoping check: General's aggregate must not just equal the whole
    # community's combined admin count.
    general_memberships = db_session.execute(
        select(GroupMembership).where(GroupMembership.group_id == general.id)
    ).scalars().all()
    expected_general_admin_count = sum(1 for m in general_memberships if m.is_admin)
    assert get_group_admin_count(db_session, general.id) == expected_general_admin_count
    if expected_general_admin_count != expected_admin_count:
        assert get_group_admin_count(db_session, general.id) != get_group_admin_count(db_session, marketplace.id)


def test_group_history_for_community_matches_per_group_queries_and_stays_ordered(db_session):
    """Batched rewrite of `get_group_history_for_community` must return the
    exact same per-group, oldest-first snapshot lists as issuing one query
    per group would."""
    provider = MockWhatsAppProvider()
    community = sync_community(db_session, provider, UNITY_WA_ID)
    sync_community(db_session, provider, UNITY_WA_ID)  # second sync -> 2 snapshots per group

    groups = {
        g.name: g for g in db_session.execute(select(Group).where(Group.community_id == community.id)).scalars()
    }

    series = get_group_history_for_community(db_session, community.id)
    series_by_name = {s.group_name: s for s in series}
    assert set(series_by_name) == set(groups)

    for name, group in groups.items():
        expected_snapshots = list(
            db_session.execute(
                select(GroupMemberSnapshot)
                .where(GroupMemberSnapshot.group_id == group.id)
                .order_by(GroupMemberSnapshot.recorded_at.asc())
            ).scalars()
        )
        actual = series_by_name[name].snapshots
        assert [s.id for s in actual] == [s.id for s in expected_snapshots]
        recorded_ats = [s.recorded_at for s in actual]
        assert recorded_ats == sorted(recorded_ats)


def test_group_history_for_community_handles_group_with_zero_snapshots(db_session):
    """A group that's never had a sync-triggered snapshot written for it must
    come back with an empty `snapshots` list, not a missing series or a
    crash."""
    provider = MockWhatsAppProvider()
    community = sync_community(db_session, provider, UNITY_WA_ID)

    empty_group = Group(
        community_id=community.id,
        wa_id="empty-history-group@g.us",
        name="Empty History Group",
        member_count=0,
    )
    db_session.add(empty_group)
    db_session.commit()

    series = get_group_history_for_community(db_session, community.id)
    empty_series = next(s for s in series if s.group_id == empty_group.id)
    assert empty_series.snapshots == []


def test_group_history_for_community_query_count_does_not_scale_with_group_count(db_session):
    """One query for the groups + one batched query for all their snapshots,
    regardless of how many groups the community has (instead of the old
    one-query-per-group approach)."""
    provider = MockWhatsAppProvider()
    community = sync_community(db_session, provider, UNITY_WA_ID)
    group_count = len(
        list(db_session.execute(select(Group).where(Group.community_id == community.id)).scalars())
    )
    assert group_count >= 3

    with _count_queries(db_session) as counter:
        get_group_history_for_community(db_session, community.id)

    assert counter["n"] <= 2
    assert counter["n"] < group_count




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
