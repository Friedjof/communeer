from datetime import UTC

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from communeer.models import Community, Group, GroupMembership, Member, MembershipStatus
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.sync.service import SyncInProgressError, sync_community

UNITY_WA_ID = "120363010000000001@g.us"
RIVERSIDE_WA_ID = "120363020000000001@g.us"


def _as_utc(dt):
    """SQLite drops tzinfo on round-trip (see `sync/service.py`'s own
    `_as_utc`) — normalize before comparing a DB-read value against a
    timezone-aware value built directly in the test, since `==` between a
    naive and an aware datetime is always `False` even for the same instant."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


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

        def get_group_invite_link(self, group_wa_id):
            return None

        def approve_join_request(self, group_wa_id, member_wa_id):
            raise NotImplementedError

        def reject_join_request(self, group_wa_id, member_wa_id):
            raise NotImplementedError

        def remove_member(self, group_wa_id, member_wa_id):
            raise NotImplementedError

        def set_member_admin(self, group_wa_id, member_wa_id, is_admin):
            raise NotImplementedError

        def send_text_message(self, member_wa_id, message):
            raise NotImplementedError

        def get_reaction_for_message(self, member_wa_id, message_id):
            raise NotImplementedError

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


def test_sync_stamps_last_message_at_forward_only_never_regresses_or_blanks(db_session):
    """`last_message_at` follows the same "set once / advance forward only"
    pattern as `joined_at`, but with a real twist: `None` from the provider
    is a genuine answer ("never posted"), not "unknown" — so a later sync
    reporting `None` (or an earlier timestamp) must never blank/regress an
    already-stored value, while a later sync reporting a genuinely *newer*
    timestamp must advance it forward."""
    from datetime import datetime, timedelta

    from communeer.providers.whatsapp.base import (
        ProviderCommunity,
        ProviderGroup,
        ProviderMember,
        ProviderMembership,
        WhatsAppConnectionStatus,
        WhatsAppProvider,
    )

    wa_id = "120363888888888888@g.us"
    group_wa_id = "120363888888888887@g.us"
    member_wa_id = "491600000001@c.us"

    class _ScriptedActivityProvider(WhatsAppProvider):
        def __init__(self, last_message_at: datetime | None) -> None:
            self.last_message_at = last_message_at

        def get_connection_status(self):
            return WhatsAppConnectionStatus(state="connected")

        def get_admin_community_wa_ids(self):
            return None

        def get_group_invite_link(self, group_wa_id):
            return None

        def approve_join_request(self, group_wa_id, member_wa_id):
            raise NotImplementedError

        def reject_join_request(self, group_wa_id, member_wa_id):
            raise NotImplementedError

        def remove_member(self, group_wa_id, member_wa_id):
            raise NotImplementedError

        def set_member_admin(self, group_wa_id, member_wa_id, is_admin):
            raise NotImplementedError

        def send_text_message(self, member_wa_id, message):
            raise NotImplementedError

        def get_reaction_for_message(self, member_wa_id, message_id):
            raise NotImplementedError

        def _community(self) -> ProviderCommunity:
            member = ProviderMember(
                wa_id=member_wa_id,
                display_name="Activity Member",
                phone_number_masked="+49 160 •••• 0001",
                first_seen_at=datetime.now(UTC),
            )
            group = ProviderGroup(
                wa_id=group_wa_id,
                name="General",
                memberships=[
                    ProviderMembership(
                        member=member, joined_at=None, last_message_at=self.last_message_at
                    )
                ],
            )
            return ProviderCommunity(wa_id=wa_id, name="Activity Community", groups=[group])

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

    older = datetime.now(UTC) - timedelta(days=30)
    newer = datetime.now(UTC) - timedelta(days=1)

    # First sync: the provider supplies a real value, and it must be stamped.
    sync_community(db_session, _ScriptedActivityProvider(older), wa_id)
    membership = db_session.execute(select(GroupMembership)).scalar_one()
    assert _as_utc(membership.last_message_at) == older

    # Second sync: the provider now reports `None` (e.g. no recent messages
    # fetched this time) — must NOT blank the already-stored value.
    sync_community(db_session, _ScriptedActivityProvider(None), wa_id)
    db_session.expire_all()
    membership = db_session.execute(select(GroupMembership)).scalar_one()
    assert _as_utc(membership.last_message_at) == older

    # Third sync: the provider reports an EARLIER timestamp than what's
    # stored — must NOT regress the stored value.
    earlier_than_stored = older - timedelta(days=10)
    sync_community(db_session, _ScriptedActivityProvider(earlier_than_stored), wa_id)
    db_session.expire_all()
    membership = db_session.execute(select(GroupMembership)).scalar_one()
    assert _as_utc(membership.last_message_at) == older

    # Fourth sync: the provider reports a genuinely NEWER timestamp — must
    # advance forward.
    sync_community(db_session, _ScriptedActivityProvider(newer), wa_id)
    db_session.expire_all()
    membership = db_session.execute(select(GroupMembership)).scalar_one()
    assert _as_utc(membership.last_message_at) == newer


def test_sync_stamps_unified_last_activity_from_chat_history_forward_only(db_session):
    """Real chat history parsed at sync time must populate the unified
    `last_activity_type/at/content` fields (this is the fix for a real gap:
    these fields used to be set *only* by the live webhook, so pre-existing
    chat history was invisible to them). Forward-only, and — critically —
    a sync backfill (always `type="message"`) must never clobber a *newer*
    `reaction` the live webhook already recorded."""
    from datetime import datetime, timedelta

    from communeer.models import ActivityType
    from communeer.providers.whatsapp.base import (
        ProviderCommunity,
        ProviderGroup,
        ProviderMember,
        ProviderMembership,
        WhatsAppConnectionStatus,
        WhatsAppProvider,
    )

    wa_id = "120363888888888889@g.us"
    group_wa_id = "120363888888888890@g.us"
    member_wa_id = "491600000002@c.us"

    class _ScriptedActivityProvider(WhatsAppProvider):
        def __init__(self, at: datetime | None, content: str | None) -> None:
            self.at = at
            self.content = content

        def get_connection_status(self):
            return WhatsAppConnectionStatus(state="connected")

        def get_admin_community_wa_ids(self):
            return None

        def get_group_invite_link(self, group_wa_id):
            return None

        def approve_join_request(self, group_wa_id, member_wa_id):
            raise NotImplementedError

        def reject_join_request(self, group_wa_id, member_wa_id):
            raise NotImplementedError

        def remove_member(self, group_wa_id, member_wa_id):
            raise NotImplementedError

        def set_member_admin(self, group_wa_id, member_wa_id, is_admin):
            raise NotImplementedError

        def send_text_message(self, member_wa_id, message):
            raise NotImplementedError

        def get_reaction_for_message(self, member_wa_id, message_id):
            raise NotImplementedError

        def _community(self) -> ProviderCommunity:
            member = ProviderMember(
                wa_id=member_wa_id,
                display_name="Activity Member",
                phone_number_masked="+49 160 •••• 0002",
                first_seen_at=datetime.now(UTC),
            )
            group = ProviderGroup(
                wa_id=group_wa_id,
                name="General",
                memberships=[
                    ProviderMembership(
                        member=member,
                        joined_at=None,
                        last_activity_type="message" if self.at else None,
                        last_activity_at=self.at,
                        last_activity_content=self.content,
                    )
                ],
            )
            return ProviderCommunity(wa_id=wa_id, name="Activity Community", groups=[group])

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

    older = datetime.now(UTC) - timedelta(days=30)
    newer = datetime.now(UTC) - timedelta(days=1)

    # First sync backfills real chat history.
    sync_community(db_session, _ScriptedActivityProvider(older, "hello from history"), wa_id)
    membership = db_session.execute(select(GroupMembership)).scalar_one()
    assert membership.last_activity_type == ActivityType.message
    assert _as_utc(membership.last_activity_at) == older
    assert membership.last_activity_content == "hello from history"

    # A live webhook reaction arrives, newer than the backfilled message —
    # simulate this the same way `webhooks/router.py` actually writes it.
    membership.last_activity_type = ActivityType.reaction
    membership.last_activity_at = newer
    membership.last_activity_content = "👍"
    db_session.commit()

    # A later sync re-runs (e.g. a manual "Sync now"), still only reporting
    # the same old message history — must NOT clobber the newer reaction.
    sync_community(db_session, _ScriptedActivityProvider(older, "hello from history"), wa_id)
    db_session.expire_all()
    membership = db_session.execute(select(GroupMembership)).scalar_one()
    assert membership.last_activity_type == ActivityType.reaction
    assert _as_utc(membership.last_activity_at) == newer
    assert membership.last_activity_content == "👍"


# ---------------------------------------------------------------------------
# sync race condition: two overlapping syncs of the same community can both
# decide the same membership is new and both attempt to insert it, tripping
# `uq_group_membership` on the losing commit.
# ---------------------------------------------------------------------------


def test_sync_community_translates_commit_integrity_error_into_sync_in_progress_error(db_session, monkeypatch):
    """Simulates the actual failure mode: the losing side of two overlapping
    syncs trips `uq_group_membership` (see `models/membership.py`) with a raw
    `IntegrityError` at commit time. Reproducing the real interleaving would
    need two genuinely concurrent transactions (SQLite's single-writer lock
    makes that impractical to provoke deterministically in a synchronous
    test), so this forces the same `IntegrityError` at the same call site
    (`db.commit()`) instead — the cleanest deterministic way to exercise
    `sync_community`'s translation of it into a clean, catchable
    `SyncInProgressError`, and to confirm the session ends up rolled back
    rather than half-committed."""
    provider = MockWhatsAppProvider()

    def _raise_integrity_error(*args, **kwargs):
        raise IntegrityError(
            "INSERT INTO group_memberships ...",
            {},
            Exception("UNIQUE constraint failed: group_memberships.group_id, group_memberships.member_id"),
        )

    monkeypatch.setattr(db_session, "commit", _raise_integrity_error)

    with pytest.raises(SyncInProgressError):
        sync_community(db_session, provider, UNITY_WA_ID)

    # The session must be left rolled back, not half-committed — nothing
    # from the failed sync should be visible.
    monkeypatch.undo()
    assert db_session.execute(select(func.count()).select_from(Community)).scalar_one() == 0
