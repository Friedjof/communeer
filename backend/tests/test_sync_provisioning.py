"""Retroactive reconciliation: `sync_community` provisions a `group_admin`
account not just for admin memberships newly discovered during *this* sync,
but for every currently-admin membership — including one that already
existed (with no linked account) before this feature shipped. See
`auth/provisioning.py::reconcile_admin_provisioning_for_group`'s docstring
for why this is a full reconciliation pass on every sync, not an edge-
triggered "only on False->True" check.

See `test_provisioning.py` for direct unit tests of the reconciliation
functions themselves; this file exercises them specifically through the
`sync_community` entry point.
"""

from sqlalchemy import select

from communeer.models import (
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


def test_resyncing_provisions_a_pre_existing_admin_that_had_no_account_yet(db_session):
    provider = MockWhatsAppProvider()
    sync_community(db_session, provider, UNITY_WA_ID)

    general = _get_group(db_session, "General")
    admin_member = _get_admin_member(db_session, general)
    provisioned = db_session.execute(select(User).where(User.member_id == admin_member.id)).scalar_one()

    # Simulate: this admin membership existed before the group_admin feature
    # shipped, so no account was ever created for it — reconstruct that
    # "before" state by deleting the account the first sync above just made.
    db_session.delete(provisioned)
    db_session.commit()
    assert db_session.execute(select(User).where(User.member_id == admin_member.id)).scalar_one_or_none() is None

    sync_community(db_session, provider, UNITY_WA_ID)

    backfilled = db_session.execute(select(User).where(User.member_id == admin_member.id)).scalar_one()
    assert backfilled.role is UserRole.group_admin
    assert backfilled.is_claimed is False


def test_resyncing_does_not_duplicate_an_already_provisioned_admins_account(db_session):
    provider = MockWhatsAppProvider()
    sync_community(db_session, provider, UNITY_WA_ID)

    general = _get_group(db_session, "General")
    admin_member = _get_admin_member(db_session, general)
    first = db_session.execute(select(User).where(User.member_id == admin_member.id)).scalar_one()

    sync_community(db_session, provider, UNITY_WA_ID)

    all_accounts = db_session.execute(select(User).where(User.member_id == admin_member.id)).scalars().all()
    assert len(all_accounts) == 1
    assert all_accounts[0].id == first.id


def test_resync_provisions_a_newly_promoted_admin(db_session):
    provider = MockWhatsAppProvider()
    sync_community(db_session, provider, UNITY_WA_ID)

    general = _get_group(db_session, "General")
    plain_membership_row = db_session.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(
            GroupMembership.group_id == general.id,
            GroupMembership.status == MembershipStatus.member,
            GroupMembership.is_admin.is_(False),
        )
    ).first()
    _membership, plain_member = plain_membership_row
    assert db_session.execute(select(User).where(User.member_id == plain_member.id)).scalar_one_or_none() is None

    # Promote them directly on the provider side — simulating a promotion
    # that happened live in WhatsApp (picked up here by the webhook-
    # triggered resync path in the real app) rather than through this app's
    # own promote button (`groups/service.py::set_group_member_admin`,
    # tested separately in `test_group_membership.py`).
    provider.set_member_admin(general.wa_id, plain_member.wa_id, True)

    sync_community(db_session, provider, UNITY_WA_ID)

    provisioned = db_session.execute(select(User).where(User.member_id == plain_member.id)).scalar_one()
    assert provisioned.role is UserRole.group_admin
    assert provisioned.is_claimed is False
