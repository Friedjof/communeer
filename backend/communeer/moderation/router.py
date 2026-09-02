import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from communeer.communities.router import get_community_or_404
from communeer.deps import get_current_user, get_db, get_provider, require_role
from communeer.groups.schemas import GroupRequestOut
from communeer.groups.service import list_group_pending_requests
from communeer.models import User, UserRole
from communeer.moderation.schemas import (
    AdminCoverageGapOut,
    CapacityAttentionOut,
    DismissModerationItemIn,
    DuplicateContentOut,
    JoinBurstOut,
    MessageBurstOut,
    ModerationQueueOut,
    NeverActiveMemberOut,
)
from communeer.moderation.service import dismiss_moderation_item, get_moderation_queue
from communeer.providers.whatsapp.base import WhatsAppProvider

# Owner/admin only, not viewer — a moderation queue is an action-oriented
# tool for the people who can actually follow up in WhatsApp, same posture as
# the audit log.
router = APIRouter(tags=["moderation"], dependencies=[Depends(require_role(UserRole.owner, UserRole.admin))])


@router.get("/communities/{community_id}/moderation/queue", response_model=ModerationQueueOut)
def get_moderation_queue_route(
    community_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
) -> ModerationQueueOut:
    community = get_community_or_404(db, community_id)
    queue = get_moderation_queue(db, community, provider)

    return ModerationQueueOut(
        admin_coverage_gaps=[
            AdminCoverageGapOut(group_id=gap.group_id, group_name=gap.group_name, admin_count=gap.admin_count)
            for gap in queue.admin_coverage_gaps
        ],
        never_active_members=[
            NeverActiveMemberOut(
                member_id=agg.member.id,
                wa_id=agg.member.wa_id,
                display_name=agg.member.display_name,
                avatar_url=agg.member.avatar_url,
                phone_number_masked=agg.member.phone_number_masked,
                group_count=agg.group_count,
                joined_at=agg.joined_at,
            )
            for agg in queue.never_active_members
        ],
        join_bursts=[
            JoinBurstOut(
                group_id=burst.group_id,
                group_name=burst.group_name,
                member_count=burst.member_count,
                recent_join_count=burst.recent_join_count,
            )
            for burst in queue.join_bursts
        ],
        capacity_attention=[
            CapacityAttentionOut(
                group_id=g.group_id,
                group_name=g.group_name,
                member_count=g.member_count,
                member_limit=g.member_limit,
                pending_request_count=g.pending_request_count,
                percent_full=g.percent_full,
                reason=g.reason,
                # Only fetched for groups that actually have pending
                # requests — `list_group_pending_requests` is one query per
                # such group, but a community only has a handful of these at
                # a time (this is the moderation queue, not a bulk list).
                pending_requests=[
                    GroupRequestOut(
                        member_id=member.id,
                        wa_id=member.wa_id,
                        display_name=member.display_name,
                        requested_at=membership.joined_at,
                    )
                    for membership, member in list_group_pending_requests(db, g.group_id)
                ]
                if g.reason in ("requests", "both")
                else [],
            )
            for g in queue.capacity_attention
        ],
        message_bursts=[
            MessageBurstOut(
                group_membership_id=burst.group_membership_id,
                group_id=burst.group_id,
                group_name=burst.group_name,
                member_id=burst.member_id,
                member_display_name=burst.member_display_name,
                member_avatar_url=burst.member_avatar_url,
                message_count=burst.message_count,
                window_minutes=burst.window_minutes,
            )
            for burst in queue.message_bursts
        ],
        duplicate_content=[
            DuplicateContentOut(
                group_membership_id=dup.group_membership_id,
                group_id=dup.group_id,
                group_name=dup.group_name,
                member_id=dup.member_id,
                member_display_name=dup.member_display_name,
                content_preview=dup.content_preview,
                occurrence_count=dup.occurrence_count,
            )
            for dup in queue.duplicate_content
        ],
    )


@router.post(
    "/communities/{community_id}/moderation/dismissals",
    status_code=status.HTTP_204_NO_CONTENT,
)
def dismiss_moderation_item_route(
    community_id: uuid.UUID,
    body: DismissModerationItemIn,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> None:
    community = get_community_or_404(db, community_id)
    dismiss_moderation_item(
        db,
        community,
        provider,
        section=body.section,
        target_id=body.target_id,
        reason=body.reason,
        actor_user_id=user.id,
    )
