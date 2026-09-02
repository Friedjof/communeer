"""`auth/provisioning.py`: idempotent auto-provisioning of `group_admin`
dashboard accounts for real WhatsApp group admins. See
`test_group_admin_permission_boundaries.py` for the full HTTP-level
consequences and `test_group_membership.py`/`test_sync_provisioning.py` for
the two write-path call sites (`groups/service.py`/`sync/service.py`).
"""

from datetime import UTC, datetime

from sqlalchemy import select

from communeer.auth.provisioning import (
    _generate_unique_username,
    ensure_group_admin_account,
    reconcile_admin_provisioning_for_group,
)
from communeer.auth.security import hash_password
from communeer.models import (
    Community,
    Group,
    GroupMembership,
    Member,
    MembershipStatus,
    User,
    UserRole,
)
from communeer.models.base import new_uuid
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"


def _sync_unity(db_session) -> Community:
    return sync_community(db_session, MockWhatsAppProvider(), UNITY_WA_ID)


def _get_group(db_session, name: str) -> Group:
    return db_session.execute(select(Group).where(Group.name == name)).scalar_one()


def _get_admin_member(db_session, group: Group) -> Member:
    row = db_session.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(
            GroupMembership.group_id == group.id,
            GroupMembership.status == MembershipStatus.member,
            GroupMembership.is_admin.is_(True),
        )
    ).first()
    return row[1]


def test_ensure_group_admin_account_is_idempotent(db_session):
    _sync_unity(db_session)
    general = _get_group(db_session, "General")
    member = _get_admin_member(db_session, general)

    # Already provisioned by the sync above — a second explicit call must
    # return the same row, not create a duplicate.
    user_a, created_a = ensure_group_admin_account(db_session, member)
    user_b, created_b = ensure_group_admin_account(db_session, member)

    assert created_a is False  # sync already created it
    assert created_b is False
    assert user_a.id == user_b.id
    assert user_a.role is UserRole.group_admin
    assert user_a.is_claimed is False
    # Requires an explicit owner approval before anything is ever sent —
    # see `approve_group_admin` / this module's docstring.
    assert user_a.is_approved is False


def test_ensure_group_admin_account_resolves_username_collisions(db_session):
    _sync_unity(db_session)
    general = _get_group(db_session, "General")
    events = _get_group(db_session, "Events")
    member_a = _get_admin_member(db_session, general)
    member_b = _get_admin_member(db_session, events)

    # Force a name collision deterministically, regardless of what the mock
    # fixture happens to name these two people, then re-provision member_b
    # under that colliding name to exercise the actual resolution path in
    # `ensure_group_admin_account` (its account from `_sync_unity` above
    # already exists under its original, non-colliding username).
    member_b.display_name = member_a.display_name
    db_session.commit()
    existing = db_session.execute(select(User).where(User.member_id == member_b.id)).scalar_one()
    db_session.delete(existing)
    db_session.commit()

    user_a = db_session.execute(select(User).where(User.member_id == member_a.id)).scalar_one()
    user_b, created_b = ensure_group_admin_account(db_session, member_b)

    assert created_b is True
    assert user_b.username != user_a.username
    assert user_b.username == f"{user_a.username}-2"


def test_generate_unique_username_appends_incrementing_suffix(db_session):
    base_username = _generate_unique_username(db_session, "Ada Lovelace")
    assert base_username == "ada-lovelace"

    db_session.add(User(username=base_username, password_hash=hash_password("x"), role=UserRole.viewer))
    db_session.commit()

    next_username = _generate_unique_username(db_session, "Ada Lovelace")
    assert next_username == "ada-lovelace-2"


def test_reconcile_provisions_all_current_admins_of_a_group(db_session):
    _sync_unity(db_session)
    general = _get_group(db_session, "General")

    admin_member_ids = {
        member_id
        for member_id, in db_session.execute(
            select(GroupMembership.member_id).where(
                GroupMembership.group_id == general.id, GroupMembership.is_admin.is_(True)
            )
        ).all()
    }
    assert admin_member_ids, "mock fixture must have at least one admin in General"

    provisioned_member_ids = {
        member_id
        for member_id, in db_session.execute(
            select(User.member_id).where(User.member_id.in_(admin_member_ids))
        ).all()
    }
    assert provisioned_member_ids == admin_member_ids


def test_reconcile_never_sends_a_message(db_session):
    """Discovering/syncing a real admin must never be the thing that sends
    a message on its own — see this module's docstring and the incident
    that motivated it. Only `approve_group_admin` (an explicit owner
    action, tested in `test_users.py`) ever calls `send_claim_code`."""
    member = Member(
        id=new_uuid(),
        wa_id="49000000001@c.us",
        display_name="Test Admin",
        first_seen_at=datetime.now(UTC),
    )
    db_session.add(member)
    db_session.flush()

    community = Community(wa_id="9999@g.us", name="Test Community")
    db_session.add(community)
    db_session.flush()
    group = Group(wa_id="9999-1@g.us", name="Test Group", community_id=community.id)
    db_session.add(group)
    db_session.flush()
    db_session.add(
        GroupMembership(group_id=group.id, member_id=member.id, is_admin=True, status=MembershipStatus.member)
    )
    db_session.commit()

    reconcile_admin_provisioning_for_group(db_session, group.id)

    user = db_session.execute(select(User).where(User.member_id == member.id)).scalar_one()
    assert user.is_claimed is False
    assert user.is_approved is False
    assert user.pending_otp_sent_at is None  # nothing was ever sent
