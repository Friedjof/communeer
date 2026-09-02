"""Derived "community membership" queries.

`CommunityMembership` is intentionally not a stored table (see
`models/membership.py`'s docstring) — everything here is computed from
`GroupMembership` rows at read time: a member's community-admin status is
defined as being an admin of that community's *announcement* group.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from communeer.models import (
    ActivityType,
    Community,
    CommunityMemberSnapshot,
    Group,
    GroupMembership,
    GroupMemberSnapshot,
    Member,
    MembershipStatus,
)


def get_group_ids_for_community(db: Session, community_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.execute(select(Group.id).where(Group.community_id == community_id)).scalars().all())


def get_announcement_group_id(db: Session, community: Community) -> uuid.UUID | None:
    if community.announcement_group_wa_id is None:
        return None
    return db.execute(
        select(Group.id).where(Group.wa_id == community.announcement_group_wa_id)
    ).scalar_one_or_none()


def get_community_admin_count(db: Session, community_id: uuid.UUID) -> int:
    """Distinct members who are admin of at least one group in this community."""
    group_ids = get_group_ids_for_community(db, community_id)
    if not group_ids:
        return 0
    return db.execute(
        select(func.count(func.distinct(GroupMembership.member_id))).where(
            GroupMembership.group_id.in_(group_ids),
            GroupMembership.is_admin.is_(True),
        )
    ).scalar_one()


def get_group_admin_count(db: Session, group_id: uuid.UUID) -> int:
    """Members who are admin of this one group."""
    return db.execute(
        select(func.count(func.distinct(GroupMembership.member_id))).where(
            GroupMembership.group_id == group_id,
            GroupMembership.is_admin.is_(True),
        )
    ).scalar_one()


def get_group_last_message_at(db: Session, group_id: uuid.UUID) -> datetime | None:
    """Most recent `last_message_at` across this group's memberships."""
    return db.execute(
        select(func.max(GroupMembership.last_message_at)).where(GroupMembership.group_id == group_id)
    ).scalar_one()


def get_community_pending_request_count(db: Session, community_id: uuid.UUID) -> int:
    group_ids = get_group_ids_for_community(db, community_id)
    if not group_ids:
        return 0
    return db.execute(
        select(func.count()).select_from(GroupMembership).where(
            GroupMembership.group_id.in_(group_ids),
            GroupMembership.status == MembershipStatus.pending,
        )
    ).scalar_one()


@dataclass
class MemberAggregate:
    member: Member
    is_admin: bool
    is_community_admin: bool
    group_count: int
    joined_at: datetime | None
    last_message_at: datetime | None
    last_seen_at: datetime | None
    # Unified "last activity" (message/reaction/view), aggregated the same
    # way as last_message_at/last_seen_at above (latest across this
    # community's groups) — whichever membership carries the most recent
    # last_activity_at wins, and its type+content come along together (never
    # mixed-and-matched from two different memberships).
    last_activity_type: ActivityType | None
    last_activity_at: datetime | None
    last_activity_content: str | None


def list_community_members(
    db: Session, community: Community, *, group_ids_filter: set[uuid.UUID] | None = None
) -> list[MemberAggregate]:
    """Every member of `community` (status == "member" in at least one of its
    groups), with admin/community-admin/group-count aggregates computed
    across that community's groups only.

    `joined_at` is the *earliest* group-join date within this community
    specifically — not the member's global `first_seen_at` — since a member
    can belong to multiple communities (the mock fixture deliberately has
    overlap) and their global first-seen date could reflect a different
    community entirely.

    `last_message_at`/`last_seen_at` are the *latest* activity across this
    community's groups (same "per-community, not global" reasoning as
    `joined_at` — just max instead of min, since more-recent activity in any
    one of a member's groups is the more relevant signal).

    `group_ids_filter`: when given, narrows the aggregation to only these
    groups within the community — used by `communities/router.py` to scope
    a `group_admin`'s view down to the group(s) they administer. `None` (the
    default, used by every owner/admin/viewer call site) is a complete no-op.
    """
    group_ids = get_group_ids_for_community(db, community.id)
    if group_ids_filter is not None:
        group_ids = [g for g in group_ids if g in group_ids_filter]
    if not group_ids:
        return []

    announcement_group_id = get_announcement_group_id(db, community)

    rows = db.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(GroupMembership.group_id.in_(group_ids), GroupMembership.status == MembershipStatus.member)
    ).all()

    aggregates: dict[uuid.UUID, MemberAggregate] = {}
    for membership, member in rows:
        agg = aggregates.get(member.id)
        if agg is None:
            agg = MemberAggregate(
                member=member,
                is_admin=False,
                is_community_admin=False,
                group_count=0,
                joined_at=None,
                last_message_at=None,
                last_seen_at=None,
                last_activity_type=None,
                last_activity_at=None,
                last_activity_content=None,
            )
            aggregates[member.id] = agg
        agg.group_count += 1
        if membership.is_admin:
            agg.is_admin = True
            if announcement_group_id is not None and membership.group_id == announcement_group_id:
                agg.is_community_admin = True
        if membership.joined_at is not None and (agg.joined_at is None or membership.joined_at < agg.joined_at):
            agg.joined_at = membership.joined_at
        if membership.last_message_at is not None and (
            agg.last_message_at is None or membership.last_message_at > agg.last_message_at
        ):
            agg.last_message_at = membership.last_message_at
        if membership.last_seen_at is not None and (
            agg.last_seen_at is None or membership.last_seen_at > agg.last_seen_at
        ):
            agg.last_seen_at = membership.last_seen_at
        if membership.last_activity_at is not None and (
            agg.last_activity_at is None or membership.last_activity_at > agg.last_activity_at
        ):
            agg.last_activity_type = membership.last_activity_type
            agg.last_activity_at = membership.last_activity_at
            agg.last_activity_content = membership.last_activity_content

    return list(aggregates.values())


def get_community_history(db: Session, community_id: uuid.UUID) -> list[CommunityMemberSnapshot]:
    """The community's growth-history data points, oldest first."""
    return list(
        db.execute(
            select(CommunityMemberSnapshot)
            .where(CommunityMemberSnapshot.community_id == community_id)
            .order_by(CommunityMemberSnapshot.recorded_at.asc())
        ).scalars()
    )


@dataclass
class GroupHistorySeries:
    group_id: uuid.UUID
    group_name: str
    snapshots: list[GroupMemberSnapshot]


def get_group_history_for_community(
    db: Session, community_id: uuid.UUID, *, group_ids_filter: set[uuid.UUID] | None = None
) -> list[GroupHistorySeries]:
    """Every group's growth-history data points, in one pass — the point of
    this endpoint is a single response the frontend can build a per-group
    comparison chart from, instead of firing one request per group.

    All snapshots for all of the community's groups are fetched in a single
    query (instead of one query per group) and then split back out per group
    in Python, preserving each group's chronological (oldest-first) order.

    `group_ids_filter`: see `list_community_members`'s identical parameter."""
    query = select(Group).where(Group.community_id == community_id)
    if group_ids_filter is not None:
        query = query.where(Group.id.in_(group_ids_filter))
    groups = db.execute(query.order_by(Group.name)).scalars().all()

    snapshots_by_group: dict[uuid.UUID, list[GroupMemberSnapshot]] = {}
    if groups:
        rows = db.execute(
            select(GroupMemberSnapshot)
            .where(GroupMemberSnapshot.group_id.in_([group.id for group in groups]))
            .order_by(GroupMemberSnapshot.group_id, GroupMemberSnapshot.recorded_at.asc())
        ).scalars()
        for snapshot in rows:
            snapshots_by_group.setdefault(snapshot.group_id, []).append(snapshot)

    return [
        GroupHistorySeries(group_id=group.id, group_name=group.name, snapshots=snapshots_by_group.get(group.id, []))
        for group in groups
    ]
