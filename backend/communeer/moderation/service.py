"""Moderation queue: a read-only aggregation over already-synced DB data.

No WhatsApp write of any kind happens here or is ever triggered from here —
this module only surfaces candidates for a human admin to act on manually in
WhatsApp itself, the same posture already established by
`renewals/service.py`. Every section is scoped to
`WhatsAppProvider.get_admin_community_wa_ids()` the same way
`communities/router.py`'s community list already is: a community the
connected account can't actually act on in WhatsApp never shows fabricated
"needs attention" data here (empty result instead).

Explicitly out of scope (see the approved plan): per-member message-frequency
or spam-burst detection, and duplicate-content detection — neither is
possible with what's stored (only the *latest* activity per membership, never
a history of messages).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from communeer.communities.service import (
    MemberAggregate,
    get_group_admin_count,
    list_community_members,
)
from communeer.errors import bad_request, not_found
from communeer.models import (
    AuditEvent,
    Community,
    Group,
    GroupMembership,
    MembershipStatus,
    ModerationDismissal,
)
from communeer.providers.whatsapp.base import WhatsAppProvider

# The four `ModerationQueueData` section names — also the only valid
# `section` values for `dismiss_moderation_item()` and the wire-level
# `DismissModerationItemIn.section` literal.
MODERATION_SECTIONS = (
    "admin_coverage_gaps",
    "never_active_members",
    "join_bursts",
    "capacity_attention",
)

# Groups with this many admins or fewer are a single point of failure: if the
# one admin leaves/is removed, nobody left in the group can moderate it.
ADMIN_COVERAGE_MAX_ADMINS = 1

# Mirrors `CAPACITY_ATTENTION_THRESHOLD` in
# `frontend/src/components/data/CapacityBar.tsx` exactly (90%) — same signal,
# now also available server-side for a cross-section queue instead of only a
# client-computed list scoped to one already-fetched community page.
CAPACITY_ATTENTION_THRESHOLD = 90

# "Rapid join burst" heuristic: a real, `joined_at`-derived flood/spam signal
# that's otherwise nowhere visible today. Two conditions must *both* hold so
# a brand-new, still-tiny group doesn't get flagged just because its first
# handful of members all joined "recently" relative to a near-zero base:
#   - at least JOIN_BURST_MIN_FRACTION of the group's *current* members
#     joined within the last JOIN_BURST_WINDOW, AND
#   - at least JOIN_BURST_MIN_ABSOLUTE members did so in absolute terms.
JOIN_BURST_WINDOW = timedelta(hours=24)
JOIN_BURST_MIN_FRACTION = 0.3
JOIN_BURST_MIN_ABSOLUTE = 5


def _ensure_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip (see `renewals/service.py`'s
    identically-named helper for the same reasoning) — every datetime this
    module stores is UTC by convention, so a naive value read back is
    re-tagged as UTC rather than compared naively against a timezone-aware
    `datetime.now(UTC)` (which would raise `TypeError`)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@dataclass
class AdminCoverageGap:
    group_id: uuid.UUID
    group_name: str
    admin_count: int


@dataclass
class JoinBurstGroup:
    group_id: uuid.UUID
    group_name: str
    member_count: int
    recent_join_count: int


@dataclass
class CapacityAttentionGroup:
    group_id: uuid.UUID
    group_name: str
    member_count: int
    member_limit: int | None
    pending_request_count: int
    percent_full: float | None
    reason: Literal["capacity", "requests", "both"]


@dataclass
class ModerationQueueData:
    admin_coverage_gaps: list[AdminCoverageGap]
    never_active_members: list[MemberAggregate]
    join_bursts: list[JoinBurstGroup]
    capacity_attention: list[CapacityAttentionGroup]


def _get_groups_for_community(db: Session, community_id: uuid.UUID) -> list[Group]:
    return list(
        db.execute(select(Group).where(Group.community_id == community_id).order_by(Group.name)).scalars()
    )


def _get_dismissals(db: Session, community_id: uuid.UUID, section: str) -> dict[str, ModerationDismissal]:
    """Active dismissals for one section of one community, keyed by
    (string-normalized) `target_id` — one query per section per queue read,
    so the per-item filtering below is just a dict lookup."""
    rows = db.execute(
        select(ModerationDismissal).where(
            ModerationDismissal.community_id == community_id,
            ModerationDismissal.section == section,
        )
    ).scalars()
    return {d.target_id: d for d in rows}


def _parse_target_uuid(target_id: str) -> uuid.UUID:
    """`target_id` arrives over the wire as a plain string (see
    `DismissModerationItemIn`) — every current section's targets happen to be
    UUIDs (group/member ids), so this both validates the shape and gives back
    something usable in a `select(...).where(Model.id == ...)`."""
    try:
        return uuid.UUID(target_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise not_found("Target not found in this community.") from exc


def _get_admin_counts_by_group(db: Session, group_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Distinct admin-member count per group, in one grouped query instead of
    one `get_group_admin_count()` round trip per group. A group with no admin
    memberships at all has no row in the result — callers must default a
    missing group_id to 0."""
    if not group_ids:
        return {}
    rows = db.execute(
        select(GroupMembership.group_id, func.count(func.distinct(GroupMembership.member_id)))
        .where(
            GroupMembership.group_id.in_(group_ids),
            GroupMembership.is_admin.is_(True),
        )
        .group_by(GroupMembership.group_id)
    ).all()
    return dict(rows)


def get_admin_coverage_gaps(db: Session, community: Community) -> list[AdminCoverageGap]:
    """Groups where at most `ADMIN_COVERAGE_MAX_ADMINS` members are admin —
    a single point of failure if that one admin leaves or is removed.

    A dismissed group is suppressed unless its current `admin_count` has
    dropped *below* the value it had at dismissal time (i.e. it got worse)."""
    dismissals = _get_dismissals(db, community.id, "admin_coverage_gaps")
    groups = _get_groups_for_community(db, community.id)
    admin_counts_by_group = _get_admin_counts_by_group(db, [group.id for group in groups])
    gaps = []
    for group in groups:
        admin_count = admin_counts_by_group.get(group.id, 0)
        if admin_count <= ADMIN_COVERAGE_MAX_ADMINS:
            dismissal = dismissals.get(str(group.id))
            if dismissal is not None:
                snapshot_admin_count = (dismissal.metric_snapshot or {}).get("adminCount")
                if snapshot_admin_count is None or admin_count >= snapshot_admin_count:
                    continue  # not worse than when dismissed — stay suppressed
            gaps.append(AdminCoverageGap(group_id=group.id, group_name=group.name, admin_count=admin_count))
    return sorted(gaps, key=lambda g: (g.admin_count, g.group_name))


def get_never_active_members(db: Session, community: Community) -> list[MemberAggregate]:
    """Every community member (across all its groups) who has never posted
    (`last_message_at is None`), excluding admins — the same "never posted"
    signal and admin exclusion `get_renewal_suggestions()` already
    establishes, just gathered as its own moderation section rather than only
    surfacing as a renewal candidate.

    This is a binary "never posted" signal with no numeric "worse" concept,
    so a dismissed member is suppressed unconditionally — it naturally exits
    this list for good once they DO post (at which point the stale dismissal
    row becomes moot; nothing needs to clean it up)."""
    dismissals = _get_dismissals(db, community.id, "never_active_members")
    aggregates = list_community_members(db, community)
    eligible = [
        a
        for a in aggregates
        if not a.is_admin
        and not a.is_community_admin
        and a.last_message_at is None
        and str(a.member.id) not in dismissals
    ]
    return sorted(eligible, key=lambda a: (a.joined_at is None, a.joined_at))


def get_join_burst_groups(db: Session, community: Community) -> list[JoinBurstGroup]:
    """Groups where an unusually high share of current members joined within
    `JOIN_BURST_WINDOW` — see the module docstring for the exact thresholds
    and why both a fraction and an absolute minimum are required.

    A dismissed group is suppressed unless its current `recent_join_count`
    has grown past the value it had at dismissal time."""
    dismissals = _get_dismissals(db, community.id, "join_bursts")
    now = datetime.now(UTC)
    window_start = now - JOIN_BURST_WINDOW

    groups = _get_groups_for_community(db, community.id)
    joined_ats_by_group: dict[uuid.UUID, list[datetime | None]] = {}
    if groups:
        rows = db.execute(
            select(GroupMembership.group_id, GroupMembership.joined_at).where(
                GroupMembership.group_id.in_([group.id for group in groups]),
                GroupMembership.status == MembershipStatus.member,
            )
        ).all()
        for group_id, joined_at in rows:
            joined_ats_by_group.setdefault(group_id, []).append(joined_at)

    results = []
    for group in groups:
        joined_ats = joined_ats_by_group.get(group.id, [])
        member_count = len(joined_ats)
        if member_count == 0:
            continue

        recent_join_count = sum(1 for j in joined_ats if j is not None and _ensure_utc(j) >= window_start)
        if recent_join_count < JOIN_BURST_MIN_ABSOLUTE:
            continue
        if recent_join_count / member_count < JOIN_BURST_MIN_FRACTION:
            continue

        dismissal = dismissals.get(str(group.id))
        if dismissal is not None:
            snapshot_recent_join_count = (dismissal.metric_snapshot or {}).get("recentJoinCount")
            if snapshot_recent_join_count is None or recent_join_count <= snapshot_recent_join_count:
                continue  # not worse than when dismissed — stay suppressed

        results.append(
            JoinBurstGroup(
                group_id=group.id,
                group_name=group.name,
                member_count=member_count,
                recent_join_count=recent_join_count,
            )
        )

    return sorted(results, key=lambda r: r.recent_join_count / r.member_count, reverse=True)


def get_capacity_attention_groups(db: Session, community: Community) -> list[CapacityAttentionGroup]:
    """Groups at/above `CAPACITY_ATTENTION_THRESHOLD` capacity or with a
    pending join request — the same two reasons `NeedsAttentionList.tsx`
    already flags per-community, now available for a cross-community queue
    too. `percent_full` matches the frontend's `formatPercent` rounding
    (one decimal place) so the two never silently disagree.

    A dismissed group is suppressed unless *either* metric has gotten worse
    since dismissal: current `percent_full` above the snapshotted value, or
    current `pending_request_count` above the snapshotted value."""
    dismissals = _get_dismissals(db, community.id, "capacity_attention")
    results = []
    for group in _get_groups_for_community(db, community.id):
        percent_full: float | None = None
        is_capacity = False
        if group.member_limit:
            percent_full = round(group.member_count / group.member_limit * 1000) / 10
            is_capacity = percent_full >= CAPACITY_ATTENTION_THRESHOLD

        is_requests = group.pending_request_count > 0
        if not is_capacity and not is_requests:
            continue

        reason: Literal["capacity", "requests", "both"]
        if is_capacity and is_requests:
            reason = "both"
        elif is_capacity:
            reason = "capacity"
        else:
            reason = "requests"

        dismissal = dismissals.get(str(group.id))
        if dismissal is not None:
            snapshot = dismissal.metric_snapshot or {}
            snapshot_percent_full = snapshot.get("percentFull")
            snapshot_pending_count = snapshot.get("pendingRequestCount")
            percent_worse = (
                percent_full is not None
                and snapshot_percent_full is not None
                and percent_full > snapshot_percent_full
            )
            pending_worse = (
                snapshot_pending_count is not None and group.pending_request_count > snapshot_pending_count
            )
            if not percent_worse and not pending_worse:
                continue  # not worse than when dismissed — stay suppressed

        results.append(
            CapacityAttentionGroup(
                group_id=group.id,
                group_name=group.name,
                member_count=group.member_count,
                member_limit=group.member_limit,
                pending_request_count=group.pending_request_count,
                percent_full=percent_full,
                reason=reason,
            )
        )

    return results


def dismiss_moderation_item(
    db: Session,
    community: Community,
    provider: WhatsAppProvider,
    section: str,
    target_id: str,
    reason: str | None,
    actor_user_id: uuid.UUID | None,
) -> ModerationDismissal:
    """Dismiss (or re-dismiss) one moderation-queue item.

    Scoped to `provider.get_admin_community_wa_ids()` exactly like
    `get_moderation_queue()` above — a community the connected WhatsApp
    account doesn't administer can't have its moderation items dismissed
    either, not just read. Unlike the read path (which degrades to an
    all-empty result), there's no "empty" to fall back to here, so this
    rejects with `not_found()` instead.

    The current metric for `target_id` is re-derived server-side the same
    way the corresponding `get_*` function computes it — a client-supplied
    snapshot is never trusted — and upserted into a `ModerationDismissal` row
    keyed by `(community_id, section, target_id)`: dismissing an
    already-dismissed item updates that same row (new snapshot/reason/
    timestamp/actor) rather than creating a duplicate or erroring.
    """
    admin_wa_ids = provider.get_admin_community_wa_ids()
    if admin_wa_ids is not None and community.wa_id not in admin_wa_ids:
        raise not_found("Community not found.")

    if section not in MODERATION_SECTIONS:
        raise bad_request(f"Unknown moderation section: {section!r}")

    if section == "admin_coverage_gaps":
        target_type = "group"
        group = db.execute(
            select(Group).where(Group.id == _parse_target_uuid(target_id), Group.community_id == community.id)
        ).scalar_one_or_none()
        if group is None:
            raise not_found("Group not found in this community.")
        metric_snapshot = {"adminCount": get_group_admin_count(db, group.id)}
        normalized_target_id = str(group.id)

    elif section == "never_active_members":
        target_type = "member"
        parsed_member_id = _parse_target_uuid(target_id)
        aggregate = next(
            (a for a in list_community_members(db, community) if a.member.id == parsed_member_id), None
        )
        if aggregate is None:
            raise not_found("Member not found in this community.")
        metric_snapshot = {}
        normalized_target_id = str(parsed_member_id)

    elif section == "join_bursts":
        target_type = "group"
        group = db.execute(
            select(Group).where(Group.id == _parse_target_uuid(target_id), Group.community_id == community.id)
        ).scalar_one_or_none()
        if group is None:
            raise not_found("Group not found in this community.")
        now = datetime.now(UTC)
        window_start = now - JOIN_BURST_WINDOW
        joined_ats = list(
            db.execute(
                select(GroupMembership.joined_at).where(
                    GroupMembership.group_id == group.id,
                    GroupMembership.status == MembershipStatus.member,
                )
            ).scalars()
        )
        recent_join_count = sum(1 for j in joined_ats if j is not None and _ensure_utc(j) >= window_start)
        metric_snapshot = {"recentJoinCount": recent_join_count, "memberCount": len(joined_ats)}
        normalized_target_id = str(group.id)

    else:  # capacity_attention
        target_type = "group"
        group = db.execute(
            select(Group).where(Group.id == _parse_target_uuid(target_id), Group.community_id == community.id)
        ).scalar_one_or_none()
        if group is None:
            raise not_found("Group not found in this community.")
        percent_full: float | None = None
        if group.member_limit:
            percent_full = round(group.member_count / group.member_limit * 1000) / 10
        metric_snapshot = {"percentFull": percent_full, "pendingRequestCount": group.pending_request_count}
        normalized_target_id = str(group.id)

    existing = db.execute(
        select(ModerationDismissal).where(
            ModerationDismissal.community_id == community.id,
            ModerationDismissal.section == section,
            ModerationDismissal.target_id == normalized_target_id,
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing is not None:
        existing.metric_snapshot = metric_snapshot
        existing.reason = reason
        existing.dismissed_by_user_id = actor_user_id
        existing.dismissed_at = now
        dismissal = existing
    else:
        dismissal = ModerationDismissal(
            community_id=community.id,
            section=section,
            target_id=normalized_target_id,
            metric_snapshot=metric_snapshot,
            reason=reason,
            dismissed_by_user_id=actor_user_id,
            dismissed_at=now,
        )
        db.add(dismissal)

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="moderation.dismissed",
            target_type=target_type,
            target_id=normalized_target_id,
            detail={"section": section, "reason": reason},
        )
    )

    db.commit()
    db.refresh(dismissal)
    return dismissal


def get_moderation_queue(db: Session, community: Community, provider: WhatsAppProvider) -> ModerationQueueData:
    """The full four-section moderation queue for one community, or an
    all-empty result if the connected WhatsApp account doesn't administer
    this community (mirrors `communities/router.py`'s `list_communities`
    filtering exactly — see module docstring)."""
    admin_wa_ids = provider.get_admin_community_wa_ids()
    if admin_wa_ids is not None and community.wa_id not in admin_wa_ids:
        return ModerationQueueData(
            admin_coverage_gaps=[],
            never_active_members=[],
            join_bursts=[],
            capacity_attention=[],
        )

    return ModerationQueueData(
        admin_coverage_gaps=get_admin_coverage_gaps(db, community),
        never_active_members=get_never_active_members(db, community),
        join_bursts=get_join_burst_groups(db, community),
        capacity_attention=get_capacity_attention_groups(db, community),
    )
