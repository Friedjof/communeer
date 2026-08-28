import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.deps import get_current_user, get_db
from communeer.errors import not_found
from communeer.groups.schemas import (
    GroupDetailAdvancedOut,
    GroupDetailOut,
    GroupMemberOut,
    GroupRequestOut,
    GroupSummaryOut,
)
from communeer.models import Group, GroupMembership, Member, MembershipStatus

router = APIRouter(tags=["groups"], dependencies=[Depends(get_current_user)])


def get_group_or_404(db: Session, group_id: uuid.UUID) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise not_found("Group not found.")
    return group


@router.get("/groups/{group_id}")
def get_group(group_id: uuid.UUID, advanced: bool = False, db: Session = Depends(get_db)) -> Response:
    group = get_group_or_404(db, group_id)
    summary = GroupSummaryOut.model_validate(group)
    if advanced:
        out = GroupDetailAdvancedOut(
            **summary.model_dump(),
            description=group.description,
            community_id=group.community_id,
            community_name=group.community.name,
            raw_metadata=group.raw_metadata,
        )
    else:
        out = GroupDetailOut(
            **summary.model_dump(),
            description=group.description,
            community_id=group.community_id,
            community_name=group.community.name,
        )
    return Response(content=out.model_dump_json(by_alias=True), media_type="application/json")


@router.get("/groups/{group_id}/members", response_model=list[GroupMemberOut])
def list_group_members(group_id: uuid.UUID, db: Session = Depends(get_db)) -> list[GroupMemberOut]:
    group = get_group_or_404(db, group_id)
    rows = db.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(GroupMembership.group_id == group.id)
        .order_by(Member.display_name)
    ).all()
    return [
        GroupMemberOut(
            member_id=member.id,
            wa_id=member.wa_id,
            display_name=member.display_name,
            avatar_url=member.avatar_url,
            is_admin=membership.is_admin,
            is_super_admin=membership.is_super_admin,
            status=membership.status,
            joined_at=membership.joined_at,
        )
        for membership, member in rows
    ]


@router.get("/groups/{group_id}/requests", response_model=list[GroupRequestOut])
def list_group_requests(group_id: uuid.UUID, db: Session = Depends(get_db)) -> list[GroupRequestOut]:
    group = get_group_or_404(db, group_id)
    rows = db.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(GroupMembership.group_id == group.id, GroupMembership.status == MembershipStatus.pending)
        .order_by(Member.display_name)
    ).all()
    return [
        GroupRequestOut(
            member_id=member.id,
            wa_id=member.wa_id,
            display_name=member.display_name,
            requested_at=membership.joined_at,
        )
        for membership, member in rows
    ]
