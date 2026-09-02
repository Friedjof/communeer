import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.authz import get_administered_group_ids
from communeer.deps import get_current_user, get_db
from communeer.errors import forbidden, not_found
from communeer.members.schemas import MemberDetailOut, MemberMembershipOut
from communeer.models import Community, Group, GroupMembership, Member, User, UserRole

router = APIRouter(tags=["members"], dependencies=[Depends(get_current_user)])


@router.get("/members/{member_id}", response_model=MemberDetailOut)
def get_member(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> MemberDetailOut:
    member = db.get(Member, member_id)
    if member is None:
        raise not_found("Member not found.")

    rows = db.execute(
        select(GroupMembership, Group, Community)
        .join(Group, Group.id == GroupMembership.group_id)
        .join(Community, Community.id == Group.community_id)
        .where(GroupMembership.member_id == member.id)
        .order_by(Community.name, Group.name)
    ).all()

    # A `group_admin` may only see this member at all if they share at least
    # one group, and even then only that member's membership rows in groups
    # the caller themselves administers — not their activity in unrelated
    # groups. 403 (not 404): the member id itself isn't secret, only the
    # cross-group detail is.
    administered_group_ids = get_administered_group_ids(db, user) if user.role is UserRole.group_admin else None
    if administered_group_ids is not None:
        if not any(group.id in administered_group_ids for _membership, group, _community in rows):
            raise forbidden("You do not have access to this member.")
        rows = [row for row in rows if row[1].id in administered_group_ids]

    memberships = [
        MemberMembershipOut(
            group_id=group.id,
            group_name=group.name,
            community_id=community.id,
            community_name=community.name,
            is_admin=membership.is_admin,
            status=membership.status,
            joined_at=membership.joined_at,
            last_activity_type=membership.last_activity_type,
            last_activity_at=membership.last_activity_at,
            last_activity_content=membership.last_activity_content,
        )
        for membership, group, community in rows
    ]

    return MemberDetailOut(
        id=member.id,
        wa_id=member.wa_id,
        display_name=member.display_name,
        phone_number_masked=member.phone_number_masked,
        avatar_url=member.avatar_url,
        is_business=member.is_business,
        first_seen_at=member.first_seen_at,
        memberships=memberships,
    )
