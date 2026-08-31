"""Group membership mutations: approve/reject join requests, remove a
member, promote/demote a group admin.

Every mutation calls the WhatsApp provider *first* and only mutates the
local DB once that succeeds — the same "provider is the source of truth"
posture `sync/service.py` already establishes, just for a single-membership
write instead of a full resync. A provider failure (see
`providers/whatsapp/base.py`'s raise-on-failure contract for these four
methods) is turned into a `service_unavailable()` `ApiError` rather than
touching the DB, so a failed WhatsApp write never desyncs local state.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from communeer.communities.service import get_group_admin_count
from communeer.errors import conflict, not_found, service_unavailable
from communeer.models import (
    AuditEvent,
    Group,
    GroupMembership,
    Member,
    MembershipStatus,
)
from communeer.providers.whatsapp.base import (
    WhatsAppNotConnectedError,
    WhatsAppProvider,
    WhatsAppProviderUnavailableError,
)


def _get_pending_membership_or_404(db: Session, group: Group, member_id: uuid.UUID) -> tuple[GroupMembership, Member]:
    row = db.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(
            GroupMembership.group_id == group.id,
            GroupMembership.member_id == member_id,
            GroupMembership.status == MembershipStatus.pending,
        )
    ).one_or_none()
    if row is None:
        raise not_found("Pending join request not found in this group.")
    return row


def _get_membership_or_404(db: Session, group: Group, member_id: uuid.UUID) -> tuple[GroupMembership, Member]:
    row = db.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(GroupMembership.group_id == group.id, GroupMembership.member_id == member_id)
    ).one_or_none()
    if row is None:
        raise not_found("Member not found in this group.")
    return row


def _recompute_group_counts(db: Session, group: Group) -> None:
    """Recompute denormalized `Group` counters from actual `GroupMembership`
    rows — never incremented/decremented in place, matching
    `sync/service.py`'s "recompute from DB rows, never trust a running
    counter" rule."""
    group.member_count = db.execute(
        select(func.count()).select_from(GroupMembership).where(
            GroupMembership.group_id == group.id, GroupMembership.status == MembershipStatus.member
        )
    ).scalar_one()
    group.pending_request_count = db.execute(
        select(func.count()).select_from(GroupMembership).where(
            GroupMembership.group_id == group.id, GroupMembership.status == MembershipStatus.pending
        )
    ).scalar_one()


def _call_provider(fn, *args) -> None:
    try:
        fn(*args)
    except (WhatsAppNotConnectedError, WhatsAppProviderUnavailableError) as exc:
        raise service_unavailable(
            "Could not reach WhatsApp to complete this action. Please try again shortly."
        ) from exc


def approve_join_request(
    db: Session, provider: WhatsAppProvider, group: Group, member_id: uuid.UUID, actor_user_id: uuid.UUID
) -> GroupMembership:
    membership, member = _get_pending_membership_or_404(db, group, member_id)

    _call_provider(provider.approve_join_request, group.wa_id, member.wa_id)

    membership.status = MembershipStatus.member
    membership.joined_at = membership.joined_at or datetime.now(UTC)
    db.flush()
    _recompute_group_counts(db, group)

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="group.request.approved",
            target_type="group_membership",
            target_id=str(member.id),
            detail={"groupId": str(group.id), "groupName": group.name},
        )
    )
    db.commit()
    db.refresh(membership)
    return membership


def reject_join_request(
    db: Session, provider: WhatsAppProvider, group: Group, member_id: uuid.UUID, actor_user_id: uuid.UUID
) -> None:
    membership, member = _get_pending_membership_or_404(db, group, member_id)

    _call_provider(provider.reject_join_request, group.wa_id, member.wa_id)

    db.delete(membership)
    db.flush()
    _recompute_group_counts(db, group)

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="group.request.rejected",
            target_type="group_membership",
            target_id=str(member.id),
            detail={"groupId": str(group.id), "groupName": group.name},
        )
    )
    db.commit()


def remove_group_member(
    db: Session, provider: WhatsAppProvider, group: Group, member_id: uuid.UUID, actor_user_id: uuid.UUID
) -> None:
    membership, member = _get_membership_or_404(db, group, member_id)

    _call_provider(provider.remove_member, group.wa_id, member.wa_id)

    db.delete(membership)
    db.flush()
    _recompute_group_counts(db, group)

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="group.member.removed",
            target_type="group_membership",
            target_id=str(member.id),
            detail={"groupId": str(group.id), "groupName": group.name},
        )
    )
    db.commit()


def set_group_member_admin(
    db: Session,
    provider: WhatsAppProvider,
    group: Group,
    member_id: uuid.UUID,
    is_admin: bool,
    actor_user_id: uuid.UUID,
) -> GroupMembership:
    membership, member = _get_membership_or_404(db, group, member_id)

    if not is_admin and membership.is_admin and get_group_admin_count(db, group.id) <= 1:
        raise conflict("Cannot demote the only remaining admin in this group.")

    if membership.is_admin == is_admin:
        return membership

    _call_provider(provider.set_member_admin, group.wa_id, member.wa_id, is_admin)

    membership.is_admin = is_admin

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="group.member.promoted" if is_admin else "group.member.demoted",
            target_type="group_membership",
            target_id=str(member.id),
            detail={"groupId": str(group.id), "groupName": group.name},
        )
    )
    db.commit()
    db.refresh(membership)
    return membership
