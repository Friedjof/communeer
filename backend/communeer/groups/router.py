import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.communities.service import (
    get_group_admin_count,
    get_group_last_message_at,
)
from communeer.deps import (
    get_current_user,
    get_db,
    get_provider,
    require_group_access,
    require_role,
)
from communeer.errors import not_found
from communeer.groups.schemas import (
    GroupDetailAdvancedOut,
    GroupDetailOut,
    GroupInviteLinkOut,
    GroupMemberOut,
    GroupMessageOut,
    GroupRequestOut,
    GroupSummaryOut,
)
from communeer.groups.service import (
    approve_join_request,
    list_group_messages,
    list_group_pending_requests,
    reject_join_request,
    remove_group_member,
    set_group_member_admin,
)
from communeer.models import (
    Group,
    GroupMembership,
    Member,
    User,
    UserRole,
)
from communeer.providers.whatsapp.base import WhatsAppProvider

router = APIRouter(
    tags=["groups"],
    # Every route below has `group_id` in its path, so this one dependency
    # covers all of them: owner/admin/viewer pass through unchanged,
    # `group_admin` is narrowed to only the group(s) they administer (see
    # `authz.py`). This is also the fix for a pre-existing gap: the GET
    # routes used to be reachable by any authenticated user regardless of
    # which group/community they had anything to do with.
    dependencies=[Depends(get_current_user), Depends(require_group_access())],
)

# Owner/admin/group_admin (within their own groups, enforced by
# `require_group_access` above) — a viewer can still read `GET .../requests`
# and `GET .../members` via the router-level `get_current_user` dependency
# above, just not act on them.
_require_manager = require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)


def get_group_or_404(db: Session, group_id: uuid.UUID) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise not_found("Group not found.")
    return group


def _group_summary(db: Session, group: Group) -> GroupSummaryOut:
    return GroupSummaryOut(
        id=group.id,
        wa_id=group.wa_id,
        name=group.name,
        description=group.description,
        picture_url=group.picture_url,
        is_announcement_group=group.is_announcement_group,
        member_count=group.member_count,
        member_limit=group.member_limit,
        pending_request_count=group.pending_request_count,
        admin_count=get_group_admin_count(db, group.id),
        last_message_at=get_group_last_message_at(db, group.id),
    )


@router.get("/groups/{group_id}")
def get_group(group_id: uuid.UUID, advanced: bool = False, db: Session = Depends(get_db)) -> Response:
    group = get_group_or_404(db, group_id)
    summary = _group_summary(db, group)
    if advanced:
        out = GroupDetailAdvancedOut(
            **summary.model_dump(),
            community_id=group.community_id,
            community_name=group.community.name,
            raw_metadata=group.raw_metadata,
        )
    else:
        out = GroupDetailOut(
            **summary.model_dump(),
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
            last_message_at=membership.last_message_at,
            last_seen_at=membership.last_seen_at,
            last_activity_type=membership.last_activity_type,
            last_activity_at=membership.last_activity_at,
            last_activity_content=membership.last_activity_content,
        )
        for membership, member in rows
    ]


@router.get(
    "/groups/{group_id}/invite-link",
    response_model=GroupInviteLinkOut,
    dependencies=[Depends(_require_manager)],
)
def get_group_invite_link_route(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
) -> GroupInviteLinkOut:
    # Deliberately fetched on demand, not embedded in `_group_summary`/the
    # group-detail response — a separate WPPConnect call nobody asked for
    # on every group page load would violate this codebase's cost posture
    # (see `wppconnect.py`'s own module docstring).
    group = get_group_or_404(db, group_id)
    return GroupInviteLinkOut(invite_link=provider.get_group_invite_link(group.wa_id))


@router.get("/groups/{group_id}/requests", response_model=list[GroupRequestOut])
def list_group_requests(group_id: uuid.UUID, db: Session = Depends(get_db)) -> list[GroupRequestOut]:
    group = get_group_or_404(db, group_id)
    rows = list_group_pending_requests(db, group.id)
    return [
        GroupRequestOut(
            member_id=member.id,
            wa_id=member.wa_id,
            display_name=member.display_name,
            requested_at=membership.joined_at,
        )
        for membership, member in rows
    ]


@router.get("/groups/{group_id}/messages", response_model=list[GroupMessageOut])
def list_group_messages_route(
    group_id: uuid.UUID,
    limit: int = 50,
    before: datetime | None = None,
    search: str | None = None,
    member_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
) -> list[GroupMessageOut]:
    # No `_require_manager` gate — a viewer can read the log, same read
    # access as `list_group_members`/`list_group_requests` above, just not
    # act on anything from it.
    group = get_group_or_404(db, group_id)
    rows = list_group_messages(db, group.id, limit=limit, before=before, search=search, member_id=member_id)
    return [
        GroupMessageOut(
            id=message.id,
            member_id=member.id if member else None,
            display_name=member.display_name if member else None,
            avatar_url=member.avatar_url if member else None,
            wa_id=member.wa_id if member else None,
            message_type=message.message_type,
            content=message.content,
            sent_at=message.sent_at,
        )
        for message, member in rows
    ]


@router.post("/groups/{group_id}/requests/{member_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
def approve_join_request_route(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(_require_manager),
) -> None:
    group = get_group_or_404(db, group_id)
    approve_join_request(db, provider, group, member_id, actor_user_id=user.id)


@router.post("/groups/{group_id}/requests/{member_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_join_request_route(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(_require_manager),
) -> None:
    group = get_group_or_404(db, group_id)
    reject_join_request(db, provider, group, member_id, actor_user_id=user.id)


@router.post("/groups/{group_id}/members/{member_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_group_member_route(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(_require_manager),
) -> None:
    group = get_group_or_404(db, group_id)
    remove_group_member(db, provider, group, member_id, actor_user_id=user.id)


@router.post("/groups/{group_id}/members/{member_id}/promote", status_code=status.HTTP_204_NO_CONTENT)
def promote_group_member_route(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(_require_manager),
) -> None:
    group = get_group_or_404(db, group_id)
    set_group_member_admin(db, provider, group, member_id, True, actor_user_id=user.id)


@router.post("/groups/{group_id}/members/{member_id}/demote", status_code=status.HTTP_204_NO_CONTENT)
def demote_group_member_route(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(_require_manager),
) -> None:
    group = get_group_or_404(db, group_id)
    set_group_member_admin(db, provider, group, member_id, False, actor_user_id=user.id)
