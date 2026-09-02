"""Direct unit tests for `authz.py` — the live-derived, per-`group_admin`
group/community access scoping. See `test_group_admin_permission_boundaries.py`
for the full HTTP-level route enumeration; this file tests the derivation
functions in isolation against `db_session` fixtures.
"""

from sqlalchemy import select

from communeer.authz import (
    ensure_community_access,
    ensure_group_access,
    get_administered_community_ids,
    get_administered_group_ids,
)
from communeer.errors import ApiError
from communeer.models import (
    Community,
    Group,
    GroupMembership,
    Member,
    MembershipStatus,
    User,
    UserRole,
)
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"


def _sync_unity(db_session) -> Community:
    return sync_community(db_session, MockWhatsAppProvider(), UNITY_WA_ID)


def _get_group(db_session, name: str) -> Group:
    return db_session.execute(select(Group).where(Group.name == name)).scalar_one()


def _get_admin_membership(db_session, group: Group) -> tuple[GroupMembership, Member]:
    row = db_session.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(
            GroupMembership.group_id == group.id,
            GroupMembership.status == MembershipStatus.member,
            GroupMembership.is_admin.is_(True),
        )
    ).first()
    return row[0], row[1]


def _make_user(db_session, *, role: UserRole, member_id=None) -> User:
    from communeer.auth.security import hash_password

    user = User(
        username=f"test-{role.value}-{uuid_hex()}",
        password_hash=hash_password("password12345"),
        role=role,
        is_active=True,
        member_id=member_id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


def test_unrestricted_roles_administer_nothing_but_are_never_blocked(db_session):
    community = _sync_unity(db_session)
    general = _get_group(db_session, "General")

    for role in (UserRole.owner, UserRole.admin, UserRole.viewer):
        user = _make_user(db_session, role=role)
        assert get_administered_group_ids(db_session, user) == set()
        assert get_administered_community_ids(db_session, user) == set()
        # Never blocked, regardless of having no administered groups.
        ensure_group_access(db_session, user, general.id)
        ensure_community_access(db_session, user, community.id)


def test_group_admin_with_no_member_link_administers_nothing(db_session):
    _sync_unity(db_session)
    general = _get_group(db_session, "General")
    user = _make_user(db_session, role=UserRole.group_admin, member_id=None)

    assert get_administered_group_ids(db_session, user) == set()
    try:
        ensure_group_access(db_session, user, general.id)
        raised = False
    except ApiError as exc:
        raised = exc.status_code == 403
    assert raised


def test_group_admin_administers_exactly_their_own_group(db_session):
    community = _sync_unity(db_session)
    general = _get_group(db_session, "General")
    events = _get_group(db_session, "Events")
    _membership, member = _get_admin_membership(db_session, general)

    # `_sync_unity` above already auto-provisioned a `group_admin` `User` for
    # this admin membership (see `sync/service.py`'s reconciliation hook) —
    # fetch it rather than creating a second one, which would collide on
    # `User.member_id`'s unique constraint.
    user = db_session.execute(select(User).where(User.member_id == member.id)).scalar_one()
    assert user.role is UserRole.group_admin

    administered = get_administered_group_ids(db_session, user)
    assert general.id in administered
    assert events.id not in administered
    assert get_administered_community_ids(db_session, user) == {community.id}

    ensure_group_access(db_session, user, general.id)  # does not raise
    ensure_community_access(db_session, user, community.id)  # does not raise

    try:
        ensure_group_access(db_session, user, events.id)
        raised = False
    except ApiError as exc:
        raised = exc.status_code == 403
    assert raised, "group_admin must not have access to a group they don't administer"
