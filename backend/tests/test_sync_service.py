from datetime import UTC

from sqlalchemy import func, select

from communeer.models import Community, Group, GroupMembership, Member, MembershipStatus
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"
RIVERSIDE_WA_ID = "120363020000000001@g.us"


def test_sync_community_creates_expected_rows(db_session):
    provider = MockWhatsAppProvider()

    community = sync_community(db_session, provider, UNITY_WA_ID)

    assert community.name == "Unity Alpha"
    assert community.group_count == 4

    groups = {g.name: g for g in db_session.execute(select(Group)).scalars()}
    assert groups["Marketplace"].member_count == 981
    assert groups["Marketplace"].member_limit == 1024
    assert groups["Marketplace"].pending_request_count == 3
    assert groups["General"].member_count == 180
    assert groups["Events"].member_count == 60

    member_count = db_session.execute(select(func.count()).select_from(Member)).scalar_one()
    membership_count = db_session.execute(select(func.count()).select_from(GroupMembership)).scalar_one()
    assert member_count > 0
    assert membership_count > 0

    pending_count = db_session.execute(
        select(func.count()).select_from(GroupMembership).where(GroupMembership.status == MembershipStatus.pending)
    ).scalar_one()
    assert pending_count == 3  # only Marketplace has pending requests in Unity Alpha


def test_sync_community_second_run_is_idempotent(db_session):
    provider = MockWhatsAppProvider()

    sync_community(db_session, provider, UNITY_WA_ID)

    community_count_after_first = db_session.execute(select(func.count()).select_from(Community)).scalar_one()
    member_count_after_first = db_session.execute(select(func.count()).select_from(Member)).scalar_one()
    membership_count_after_first = db_session.execute(
        select(func.count()).select_from(GroupMembership)
    ).scalar_one()
    group_count_after_first = db_session.execute(select(func.count()).select_from(Group)).scalar_one()

    community = sync_community(db_session, provider, UNITY_WA_ID)

    community_count_after_second = db_session.execute(select(func.count()).select_from(Community)).scalar_one()
    member_count_after_second = db_session.execute(select(func.count()).select_from(Member)).scalar_one()
    membership_count_after_second = db_session.execute(
        select(func.count()).select_from(GroupMembership)
    ).scalar_one()
    group_count_after_second = db_session.execute(select(func.count()).select_from(Group)).scalar_one()

    assert community_count_after_first == community_count_after_second == 1
    assert group_count_after_first == group_count_after_second == 4
    assert member_count_after_first == member_count_after_second
    assert membership_count_after_first == membership_count_after_second
    assert community.member_count > 0


def test_sync_community_reconciles_removed_membership(db_session):
    from datetime import datetime

    provider = MockWhatsAppProvider()
    sync_community(db_session, provider, UNITY_WA_ID)

    marketplace = db_session.execute(select(Group).where(Group.name == "Marketplace")).scalar_one()

    # a member who is NOT part of Marketplace in the provider fixture (e.g.
    # only in Events) gets spuriously added to Marketplace directly in the
    # DB, simulating drift; a fresh sync against the (unchanged) mock
    # provider should hard-delete that row back out.
    events = db_session.execute(select(Group).where(Group.name == "Events")).scalar_one()
    events_member_ids = {
        gm.member_id
        for gm in db_session.execute(select(GroupMembership).where(GroupMembership.group_id == events.id)).scalars()
    }
    marketplace_member_ids = {
        gm.member_id
        for gm in db_session.execute(
            select(GroupMembership).where(GroupMembership.group_id == marketplace.id)
        ).scalars()
    }
    drifted_member_id = next(iter(events_member_ids - marketplace_member_ids))

    db_session.add(
        GroupMembership(
            group_id=marketplace.id,
            member_id=drifted_member_id,
            status=MembershipStatus.member,
            joined_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    before_count = db_session.execute(
        select(func.count())
        .select_from(GroupMembership)
        .where(GroupMembership.group_id == marketplace.id, GroupMembership.member_id == drifted_member_id)
    ).scalar_one()
    assert before_count == 1

    sync_community(db_session, provider, UNITY_WA_ID)

    after_count = db_session.execute(
        select(func.count())
        .select_from(GroupMembership)
        .where(GroupMembership.group_id == marketplace.id, GroupMembership.member_id == drifted_member_id)
    ).scalar_one()
    assert after_count == 0


def test_sync_riverside_collective(db_session):
    provider = MockWhatsAppProvider()
    community = sync_community(db_session, provider, RIVERSIDE_WA_ID)

    assert community.name == "Riverside Collective"
    groups = {g.name: g for g in db_session.execute(select(Group)).scalars()}
    assert groups["Buy & Sell"].member_count == 400
    assert groups["Buy & Sell"].member_limit == 512
    assert groups["Volunteers"].pending_request_count == 2


def test_sync_stamps_joined_at_once_and_never_blanks_it(db_session):
    """A real provider (WPPConnect) has no way to look up when an existing
    membership actually started — it always reports `joined_at=None`. The
    first sync should stamp *something* (rather than leaving it null
    forever); a later sync, still getting `None` back from the provider,
    must not erase that already-recorded date."""
    from datetime import datetime

    from communeer.providers.whatsapp.base import (
        ProviderCommunity,
        ProviderGroup,
        ProviderMember,
        ProviderMembership,
        WhatsAppConnectionStatus,
        WhatsAppProvider,
    )

    wa_id = "120363999999999999@g.us"
    group_wa_id = "120363999999999998@g.us"
    member_wa_id = "491600000000@c.us"

    class _NeverKnowsJoinDateProvider(WhatsAppProvider):
        def get_connection_status(self):
            return WhatsAppConnectionStatus(state="connected")

        def get_admin_community_wa_ids(self):
            return None

        def _community(self) -> ProviderCommunity:
            member = ProviderMember(
                wa_id=member_wa_id,
                display_name="No Join Date",
                phone_number_masked="+49 160 •••• 0000",
                first_seen_at=datetime.now(UTC),
            )
            group = ProviderGroup(
                wa_id=group_wa_id,
                name="General",
                memberships=[ProviderMembership(member=member, joined_at=None)],
            )
            return ProviderCommunity(wa_id=wa_id, name="No Join Date Community", groups=[group])

        def get_communities(self):
            return [self._community()]

        def get_community(self, wa_id):
            return self._community()

        def get_groups(self, community_wa_id):
            return self._community().groups

        def get_group(self, wa_id):
            return self._community().groups[0]

        def get_members(self, group_wa_id):
            return self._community().groups[0].memberships

    provider = _NeverKnowsJoinDateProvider()

    sync_community(db_session, provider, wa_id)
    membership = db_session.execute(select(GroupMembership)).scalar_one()
    first_joined_at = membership.joined_at
    assert first_joined_at is not None

    sync_community(db_session, provider, wa_id)
    db_session.expire_all()
    membership = db_session.execute(select(GroupMembership)).scalar_one()
    assert membership.joined_at == first_joined_at
