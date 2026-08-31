import uuid

from sqlalchemy import select

from communeer.communities.service import get_group_admin_count
from communeer.errors import ApiError
from communeer.groups.service import (
    approve_join_request,
    reject_join_request,
    remove_group_member,
    set_group_member_admin,
)
from communeer.models import Community, Group, GroupMembership, Member, MembershipStatus
from communeer.providers.whatsapp.base import WhatsAppProviderUnavailableError
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"


def _sync_unity(db_session) -> Community:
    provider = MockWhatsAppProvider()
    return sync_community(db_session, provider, UNITY_WA_ID)


def _get_group(db_session, name: str) -> Group:
    return db_session.execute(select(Group).where(Group.name == name)).scalar_one()


def _get_pending_membership(db_session, group: Group) -> tuple[GroupMembership, Member]:
    row = db_session.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(GroupMembership.group_id == group.id, GroupMembership.status == MembershipStatus.pending)
    ).first()
    return row[0], row[1]


def _get_member_membership(db_session, group: Group) -> tuple[GroupMembership, Member]:
    """A non-admin `member`-status row — excluding admins so a test that
    asserts `not membership.is_admin` (e.g. the promote/demote round trip)
    can't flakily land on one of the mock fixture's admin memberships, which
    happen to be the very first rows inserted for a group."""
    row = db_session.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(
            GroupMembership.group_id == group.id,
            GroupMembership.status == MembershipStatus.member,
            GroupMembership.is_admin.is_(False),
        )
    ).first()
    return row[0], row[1]


class _FailingProvider(MockWhatsAppProvider):
    """Same fixture data, but every write action raises — used to assert a
    failed WhatsApp write never touches the local DB."""

    def approve_join_request(self, group_wa_id: str, member_wa_id: str) -> None:
        raise WhatsAppProviderUnavailableError("boom")

    def reject_join_request(self, group_wa_id: str, member_wa_id: str) -> None:
        raise WhatsAppProviderUnavailableError("boom")

    def remove_member(self, group_wa_id: str, member_wa_id: str) -> None:
        raise WhatsAppProviderUnavailableError("boom")

    def set_member_admin(self, group_wa_id: str, member_wa_id: str, is_admin: bool) -> None:
        raise WhatsAppProviderUnavailableError("boom")


# ---------------------------------------------------------------------------
# approve/reject join requests
# ---------------------------------------------------------------------------


def test_approve_join_request_moves_pending_to_member(db_session):
    _sync_unity(db_session)
    marketplace = _get_group(db_session, "Marketplace")
    _membership, member = _get_pending_membership(db_session, marketplace)
    pending_before = marketplace.pending_request_count
    members_before = marketplace.member_count

    provider = MockWhatsAppProvider()
    result = approve_join_request(db_session, provider, marketplace, member.id, actor_user_id=None)

    assert result.status == MembershipStatus.member
    assert result.joined_at is not None
    db_session.refresh(marketplace)
    assert marketplace.pending_request_count == pending_before - 1
    assert marketplace.member_count == members_before + 1
    # provider-side mirror actually updated too
    assert provider.get_group(marketplace.wa_id).memberships
    approved_provider_membership = next(
        m for m in provider.get_group(marketplace.wa_id).memberships if m.member.wa_id == member.wa_id
    )
    assert approved_provider_membership.status == "member"


def test_reject_join_request_deletes_membership(db_session):
    _sync_unity(db_session)
    marketplace = _get_group(db_session, "Marketplace")
    _membership, member = _get_pending_membership(db_session, marketplace)
    pending_before = marketplace.pending_request_count

    provider = MockWhatsAppProvider()
    reject_join_request(db_session, provider, marketplace, member.id, actor_user_id=None)

    db_session.refresh(marketplace)
    assert marketplace.pending_request_count == pending_before - 1
    remaining = db_session.execute(
        select(GroupMembership).where(GroupMembership.group_id == marketplace.id, GroupMembership.member_id == member.id)
    ).scalar_one_or_none()
    assert remaining is None


def test_approve_join_request_not_pending_raises_not_found(db_session):
    _sync_unity(db_session)
    marketplace = _get_group(db_session, "Marketplace")
    _, active_member = _get_member_membership(db_session, marketplace)

    try:
        approve_join_request(db_session, MockWhatsAppProvider(), marketplace, active_member.id, actor_user_id=None)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 404


def test_provider_failure_on_approve_does_not_touch_db(db_session):
    _sync_unity(db_session)
    marketplace = _get_group(db_session, "Marketplace")
    _, member = _get_pending_membership(db_session, marketplace)
    pending_before = marketplace.pending_request_count

    try:
        approve_join_request(db_session, _FailingProvider(), marketplace, member.id, actor_user_id=None)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 503

    db_session.refresh(marketplace)
    assert marketplace.pending_request_count == pending_before
    still_pending = db_session.execute(
        select(GroupMembership).where(GroupMembership.group_id == marketplace.id, GroupMembership.member_id == member.id)
    ).scalar_one()
    assert still_pending.status == MembershipStatus.pending


# ---------------------------------------------------------------------------
# remove / promote / demote
# ---------------------------------------------------------------------------


def test_remove_group_member_deletes_membership_and_recomputes_count(db_session):
    _sync_unity(db_session)
    marketplace = _get_group(db_session, "Marketplace")
    _, member = _get_member_membership(db_session, marketplace)
    members_before = marketplace.member_count

    remove_group_member(db_session, MockWhatsAppProvider(), marketplace, member.id, actor_user_id=None)

    db_session.refresh(marketplace)
    assert marketplace.member_count == members_before - 1
    remaining = db_session.execute(
        select(GroupMembership).where(GroupMembership.group_id == marketplace.id, GroupMembership.member_id == member.id)
    ).scalar_one_or_none()
    assert remaining is None


def test_promote_then_demote_round_trips(db_session):
    _sync_unity(db_session)
    marketplace = _get_group(db_session, "Marketplace")
    membership, member = _get_member_membership(db_session, marketplace)
    assert not membership.is_admin

    provider = MockWhatsAppProvider()
    promoted = set_group_member_admin(db_session, provider, marketplace, member.id, True, actor_user_id=None)
    assert promoted.is_admin is True

    demoted = set_group_member_admin(db_session, provider, marketplace, member.id, False, actor_user_id=None)
    assert demoted.is_admin is False


def test_demoting_the_only_remaining_admin_is_blocked(db_session):
    _sync_unity(db_session)
    # "Events" has exactly one group admin in the mock fixture.
    events = _get_group(db_session, "Events")
    assert get_group_admin_count(db_session, events.id) == 1
    admin_membership = db_session.execute(
        select(GroupMembership).where(GroupMembership.group_id == events.id, GroupMembership.is_admin.is_(True))
    ).scalar_one()

    try:
        set_group_member_admin(
            db_session, MockWhatsAppProvider(), events, admin_membership.member_id, False, actor_user_id=None
        )
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 409

    db_session.refresh(admin_membership)
    assert admin_membership.is_admin is True


def test_remove_member_not_in_group_raises_not_found(db_session):
    _sync_unity(db_session)
    marketplace = _get_group(db_session, "Marketplace")

    try:
        remove_group_member(db_session, MockWhatsAppProvider(), marketplace, uuid.uuid4(), actor_user_id=None)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 404


# ---------------------------------------------------------------------------
# HTTP-level: role gating
# ---------------------------------------------------------------------------


def _login(client) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "changeme123"})
    assert response.status_code == 200


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


def test_approve_route_viewer_gets_403_owner_gets_204(client):
    # Deliberately targets Riverside Collective's "Volunteers" group, not
    # Unity Alpha's "Marketplace" — the shared `client`/`app` fixtures reuse
    # one process-lifetime `MockWhatsAppProvider` (see `get_provider`'s
    # `@lru_cache`), so an actual approve here permanently mutates that
    # provider's in-memory state for the rest of the test session.
    # `test_growth_snapshots.py` hardcodes Marketplace's pending/member
    # counts against a pristine fixture; Volunteers isn't asserted on by any
    # other `client`-based test, so it's safe to mutate here.
    _seed_viewer_user()
    _login(client)

    communities = client.get("/api/v1/communities").json()
    riverside = next(c for c in communities if c["name"] == "Riverside Collective")
    groups = client.get(f"/api/v1/communities/{riverside['id']}/groups").json()
    volunteers = next(g for g in groups if g["name"] == "Volunteers")
    requests = client.get(f"/api/v1/groups/{volunteers['id']}/requests").json()
    target = requests[0]

    client.post("/api/v1/auth/logout")
    viewer_login = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-123"})
    assert viewer_login.status_code == 200

    response = client.post(f"/api/v1/groups/{volunteers['id']}/requests/{target['memberId']}/approve")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    client.post("/api/v1/auth/logout")
    _login(client)

    response = client.post(f"/api/v1/groups/{volunteers['id']}/requests/{target['memberId']}/approve")
    assert response.status_code == 204

    audit = client.get("/api/v1/audit", params={"action": "group.request.approved"}).json()
    assert any(e["targetId"] == target["memberId"] for e in audit)
