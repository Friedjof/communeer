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


def list_community_members(db: Session, community: Community) -> list[MemberAggregate]:
    """Every member of `community` (status == "member" in at least one of its
    groups), with admin/community-admin/group-count aggregates computed
    across that community's groups only.

    `joined_at` is the *earliest* group-join date within this community
    specifically — not the member's global `first_seen_at` — since a member
    can belong to multiple communities (the mock fixture deliberately has
    overlap) and their global first-seen date could reflect a different
    community entirely.
    """
    group_ids = get_group_ids_for_community(db, community.id)
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
                member=member, is_admin=False, is_community_admin=False, group_count=0, joined_at=None
            )
            aggregates[member.id] = agg
        agg.group_count += 1
        if membership.is_admin:
            agg.is_admin = True
            if announcement_group_id is not None and membership.group_id == announcement_group_id:
                agg.is_community_admin = True
        if membership.joined_at is not None and (agg.joined_at is None or membership.joined_at < agg.joined_at):
            agg.joined_at = membership.joined_at

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


def get_group_history_for_community(db: Session, community_id: uuid.UUID) -> list[GroupHistorySeries]:
    """Every group's growth-history data points, in one pass — the point of
    this endpoint is a single response the frontend can build a per-group
    comparison chart from, instead of firing one request per group."""
    groups = db.execute(
        select(Group).where(Group.community_id == community_id).order_by(Group.name)
    ).scalars().all()

    series: list[GroupHistorySeries] = []
    for group in groups:
        snapshots = list(
            db.execute(
                select(GroupMemberSnapshot)
                .where(GroupMemberSnapshot.group_id == group.id)
                .order_by(GroupMemberSnapshot.recorded_at.asc())
            ).scalars()
        )
        series.append(GroupHistorySeries(group_id=group.id, group_name=group.name, snapshots=snapshots))
    return series
