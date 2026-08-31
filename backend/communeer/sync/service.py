"""`sync_community`: pull one community from a `WhatsAppProvider` and make the
local DB an exact mirror of it.

Upserts `Community`/`Group`/`Member`/`GroupMembership` by natural key
(`wa_id`, or `(group_id, member_id)` for memberships), hard-deletes
`GroupMembership` rows no longer present in the provider payload (sync means
"exact mirror of current provider state", not membership history),
recomputes every denormalized count from the DB rows that actually exist
(never trusts the provider's own counts blindly), stamps `last_synced_at`,
and writes one `AuditEvent` describing what changed.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from communeer.communities.service import (
    get_community_admin_count,
    get_community_pending_request_count,
)
from communeer.models import (
    ActivityType,
    AuditEvent,
    Community,
    CommunityMemberSnapshot,
    Group,
    GroupMembership,
    GroupMemberSnapshot,
    Member,
    MembershipStatus,
)
from communeer.models.base import new_uuid
from communeer.providers.whatsapp.base import (
    ProviderCommunity,
    ProviderMember,
    WhatsAppProvider,
)


class CommunityNotFoundError(Exception):
    """Raised when the provider has no community with the given wa_id."""


class SyncInProgressError(Exception):
    """Raised when this sync collided with a concurrent sync of the same
    community. Two overlapping syncs (a double-clicked "Sync now", or a
    manual sync racing the webhook's `onparticipantschanged`-triggered
    resync) can both decide the same membership is new and both attempt to
    insert it — only one commit wins, the other trips `uq_group_membership`
    (see `models/membership.py`). Callers should turn this into a clean,
    retryable error (409) rather than letting the raw `IntegrityError`
    propagate as a generic 500."""


def _as_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on round-trip (confirmed empirically elsewhere in
    this codebase — see `renewals/service.py`'s own `_ensure_utc`): a value
    read back via a fresh query in the same session can come back naive even
    though it was written UTC-aware. Every datetime this module compares is
    UTC by convention, so a naive value is re-tagged rather than compared
    naively against a timezone-aware value (which raises `TypeError`)."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@dataclass
class SyncStats:
    groups_created: int = 0
    groups_updated: int = 0
    members_upserted: int = 0
    memberships_upserted: int = 0
    memberships_removed: int = 0
    pending_requests_found: int = 0

    def as_dict(self) -> dict:
        return {
            "groupsCreated": self.groups_created,
            "groupsUpdated": self.groups_updated,
            "membersUpserted": self.members_upserted,
            "membershipsUpserted": self.memberships_upserted,
            "membershipsRemoved": self.memberships_removed,
            "pendingRequestsFound": self.pending_requests_found,
        }


def _upsert_member(db: Session, provider_member: ProviderMember, cache: dict[str, Member]) -> Member:
    if provider_member.wa_id in cache:
        return cache[provider_member.wa_id]

    member = db.execute(
        select(Member).where(Member.wa_id == provider_member.wa_id)
    ).scalar_one_or_none()

    if member is None:
        member = Member(
            id=new_uuid(),  # assign client-side so it's usable as an FK below without an extra flush
            wa_id=provider_member.wa_id,
            display_name=provider_member.display_name,
            phone_number_masked=provider_member.phone_number_masked,
            avatar_url=provider_member.avatar_url,
            is_business=provider_member.is_business,
            first_seen_at=provider_member.first_seen_at,
            raw_metadata=provider_member.raw,
        )
        db.add(member)
    else:
        member.display_name = provider_member.display_name
        member.phone_number_masked = provider_member.phone_number_masked
        member.avatar_url = provider_member.avatar_url
        member.is_business = provider_member.is_business
        member.raw_metadata = provider_member.raw

    cache[provider_member.wa_id] = member
    return member


def sync_community(
    db: Session,
    provider: WhatsAppProvider,
    community_wa_id: str,
    actor_user_id: uuid.UUID | None = None,
    provider_community: ProviderCommunity | None = None,
) -> Community:
    """Thin wrapper around `_sync_community_impl`: turns a concurrent-sync
    collision (see `SyncInProgressError` above) into a clean, catchable error
    instead of letting the raw `IntegrityError` propagate as a generic 500.

    `provider_community`: pass an already-fetched, fully-hydrated
    `ProviderCommunity` (e.g. one of `provider.get_communities()`'s results)
    to skip a redundant `provider.get_community(community_wa_id)` call —
    for the real WPPConnect provider, that call re-does the full, expensive
    per-group members/admins/messages fan-out (see that provider's own
    module docstring), so re-fetching a community that was just fetched a
    moment ago (as `discover_and_sync` and the boot-time priming loop both
    do) doubles real WhatsApp API cost for no benefit. Omit it (the default)
    when the caller only has a `wa_id`, e.g. the per-community "Sync now"
    button or a webhook-triggered resync."""
    try:
        return _sync_community_impl(db, provider, community_wa_id, actor_user_id, provider_community)
    except IntegrityError as exc:
        db.rollback()
        raise SyncInProgressError(community_wa_id) from exc


def _sync_community_impl(
    db: Session,
    provider: WhatsAppProvider,
    community_wa_id: str,
    actor_user_id: uuid.UUID | None = None,
    provider_community: ProviderCommunity | None = None,
) -> Community:
    if provider_community is None:
        provider_community = provider.get_community(community_wa_id)
    if provider_community is None:
        raise CommunityNotFoundError(community_wa_id)

    stats = SyncStats()
    now = datetime.now(UTC)
    member_cache: dict[str, Member] = {}

    community = db.execute(
        select(Community).where(Community.wa_id == provider_community.wa_id)
    ).scalar_one_or_none()
    if community is None:
        community = Community(wa_id=provider_community.wa_id)
        db.add(community)

    community.name = provider_community.name
    community.description = provider_community.description
    community.picture_url = provider_community.picture_url
    community.announcement_group_wa_id = provider_community.announcement_group_wa_id
    community.raw_metadata = provider_community.raw
    db.flush()  # ensure community.id exists for FKs below

    for provider_group in provider_community.groups:
        group = db.execute(
            select(Group).where(Group.wa_id == provider_group.wa_id)
        ).scalar_one_or_none()
        is_new_group = group is None
        if group is None:
            group = Group(wa_id=provider_group.wa_id, community_id=community.id)
            db.add(group)
        else:
            group.community_id = community.id

        group.name = provider_group.name
        group.description = provider_group.description
        group.picture_url = provider_group.picture_url
        group.is_announcement_group = provider_group.is_announcement_group
        group.member_limit = provider_group.member_limit
        group.raw_metadata = provider_group.raw
        group.last_synced_at = now
        db.flush()  # ensure group.id exists for FKs below

        if is_new_group:
            stats.groups_created += 1
        else:
            stats.groups_updated += 1

        existing_memberships = {
            gm.member_id: gm
            for gm in db.execute(
                select(GroupMembership).where(GroupMembership.group_id == group.id)
            ).scalars()
        }
        seen_member_ids: set[uuid.UUID] = set()

        for provider_membership in provider_group.memberships:
            member = _upsert_member(db, provider_membership.member, member_cache)
            stats.members_upserted = len(member_cache)
            seen_member_ids.add(member.id)

            membership = existing_memberships.get(member.id)
            is_new_membership = membership is None
            if membership is None:
                membership = GroupMembership(group_id=group.id, member_id=member.id)
                db.add(membership)
            membership.is_admin = provider_membership.is_admin
            membership.is_super_admin = provider_membership.is_super_admin
            membership.status = MembershipStatus(provider_membership.status)
            # A real provider (WPPConnect) has no way to look up when an
            # *existing* membership actually started — it always reports
            # `joined_at=None`. On first sight of a membership, that's the
            # best we can do: record "first observed by Communeer" (now)
            # rather than leaving it null forever. On every later sync,
            # only overwrite it if the provider actually supplies a real
            # value (Mock always does) — never blank out an already-known
            # date just because this particular call didn't return one.
            if is_new_membership:
                membership.joined_at = provider_membership.joined_at or now
            elif provider_membership.joined_at is not None:
                membership.joined_at = provider_membership.joined_at
            # `last_message_at`/`last_seen_at`: same "set once / advance
            # forward only, never regress or blank" pattern as `joined_at`
            # above — but here there's no "first observed by Communeer"
            # fallback (unlike `joined_at`, `None` is a real, honest answer:
            # "never posted"/"no presence data", not "unknown because we
            # haven't looked yet"). Only ever move these forward when the
            # provider supplies a strictly later value; a `None` or an
            # earlier value from this sync must never overwrite an
            # already-stored one.
            if provider_membership.last_message_at is not None and (
                _as_utc(membership.last_message_at) is None
                or provider_membership.last_message_at > _as_utc(membership.last_message_at)
            ):
                membership.last_message_at = provider_membership.last_message_at
            if provider_membership.last_seen_at is not None and (
                _as_utc(membership.last_seen_at) is None
                or provider_membership.last_seen_at > _as_utc(membership.last_seen_at)
            ):
                membership.last_seen_at = provider_membership.last_seen_at
            # Unified "last activity" — same forward-only rule, compared
            # against `last_activity_at` specifically (not `last_message_at`
            # above): a provider sync can only ever supply `type="message"`
            # (parsed chat history), so this never overwrites a *newer*
            # reaction the live webhook already recorded — it only fills in
            # activity a sync can see that the webhook hasn't captured yet
            # (e.g. history that predates the webhook being wired up at all).
            if provider_membership.last_activity_at is not None and (
                _as_utc(membership.last_activity_at) is None
                or provider_membership.last_activity_at > _as_utc(membership.last_activity_at)
            ):
                membership.last_activity_type = ActivityType(provider_membership.last_activity_type)
                membership.last_activity_at = provider_membership.last_activity_at
                membership.last_activity_content = provider_membership.last_activity_content
            stats.memberships_upserted += 1
            if membership.status == MembershipStatus.pending:
                stats.pending_requests_found += 1

        # hard-delete reconcile: memberships no longer present in the
        # provider payload for this group.
        for member_id, membership in existing_memberships.items():
            if member_id not in seen_member_ids:
                db.delete(membership)
                stats.memberships_removed += 1

        db.flush()

        # recompute denormalized counts from the DB, not the provider.
        group.member_count = db.execute(
            select(func.count())
            .select_from(GroupMembership)
            .where(GroupMembership.group_id == group.id, GroupMembership.status == MembershipStatus.member)
        ).scalar_one()
        group.pending_request_count = db.execute(
            select(func.count())
            .select_from(GroupMembership)
            .where(GroupMembership.group_id == group.id, GroupMembership.status == MembershipStatus.pending)
        ).scalar_one()

        # one growth-history data point per group per sync — never
        # deduplicated, that repetition across syncs *is* the time series.
        db.add(
            GroupMemberSnapshot(
                group_id=group.id,
                member_count=group.member_count,
                pending_request_count=group.pending_request_count,
                recorded_at=now,
            )
        )

    db.flush()

    # recompute community-level counts from the DB.
    community_group_ids = db.execute(
        select(Group.id).where(Group.community_id == community.id)
    ).scalars().all()

    if community_group_ids:
        community.member_count = db.execute(
            select(func.count(func.distinct(GroupMembership.member_id)))
            .where(
                GroupMembership.group_id.in_(community_group_ids),
                GroupMembership.status == MembershipStatus.member,
            )
        ).scalar_one()
    else:
        community.member_count = 0
    community.group_count = len(community_group_ids)
    community.last_synced_at = now

    # one growth-history data point for the community per sync, same
    # reasoning as the per-group snapshots above.
    db.add(
        CommunityMemberSnapshot(
            community_id=community.id,
            member_count=community.member_count,
            group_count=community.group_count,
            admin_count=get_community_admin_count(db, community.id),
            pending_request_count=get_community_pending_request_count(db, community.id),
            recorded_at=now,
        )
    )

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="community.sync",
            target_type="community",
            target_id=str(community.id),
            detail=stats.as_dict(),
        )
    )

    db.commit()
    db.refresh(community)
    return community
