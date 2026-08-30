import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from communeer.communities.router import get_community_or_404
from communeer.deps import get_current_user, get_db, get_provider, require_role
from communeer.models import User, UserRole
from communeer.moderation.schemas import (
    AdminCoverageGapOut,
    CapacityAttentionOut,
    DismissModerationItemIn,
    JoinBurstOut,
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
            )
            for g in queue.capacity_attention
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
