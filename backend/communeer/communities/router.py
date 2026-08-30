import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.communities.schemas import (
    CommunityDetailAdvancedOut,
    CommunityDetailOut,
    CommunityHistoryPointOut,
    CommunitySummaryOut,
    GroupHistoryPointOut,
    GroupHistorySeriesOut,
    MemberSummaryOut,
)
from communeer.communities.service import (
    get_community_admin_count,
    get_community_history,
    get_community_pending_request_count,
    get_group_admin_count,
    get_group_history_for_community,
    get_group_last_message_at,
    list_community_members,
)
from communeer.deps import get_current_user, get_db, get_provider
from communeer.errors import not_found
from communeer.groups.schemas import GroupSummaryOut
from communeer.models import Community, Group
from communeer.providers.whatsapp.base import WhatsAppProvider

router = APIRouter(tags=["communities"], dependencies=[Depends(get_current_user)])


def get_community_or_404(db: Session, community_id: uuid.UUID) -> Community:
    community = db.get(Community, community_id)
    if community is None:
        raise not_found("Community not found.")
    return community


def _summary(db: Session, community: Community) -> CommunitySummaryOut:
    return CommunitySummaryOut(
        id=community.id,
        wa_id=community.wa_id,
        name=community.name,
        picture_url=community.picture_url,
        member_count=community.member_count,
        group_count=community.group_count,
        admin_count=get_community_admin_count(db, community.id),
        pending_request_count=get_community_pending_request_count(db, community.id),
        last_synced_at=community.last_synced_at,
    )


@router.get("/communities", response_model=list[CommunitySummaryOut])
def list_communities(
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
) -> list[CommunitySummaryOut]:
    communities = db.execute(select(Community).order_by(Community.name)).scalars().all()

    # `None` means "can't determine / not applicable" — show everything,
    # exactly as before this filter existed (this is what mock mode always
    # returns). A non-`None` set means the connected account's own admin
    # standing IS known, so narrow the list down to only what it can
    # actually act on.
    admin_wa_ids = provider.get_admin_community_wa_ids()
    if admin_wa_ids is not None:
        communities = [c for c in communities if c.wa_id in admin_wa_ids]

    return [_summary(db, c) for c in communities]


@router.get("/communities/{community_id}")
def get_community(
    community_id: uuid.UUID,
    advanced: bool = False,
    db: Session = Depends(get_db),
) -> Response:
    community = get_community_or_404(db, community_id)
    summary = _summary(db, community)
    if advanced:
        out = CommunityDetailAdvancedOut(
            **summary.model_dump(),
            description=community.description,
            announcement_group_wa_id=community.announcement_group_wa_id,
            raw_metadata=community.raw_metadata,
        )
    else:
        out = CommunityDetailOut(
            **summary.model_dump(),
            description=community.description,
            announcement_group_wa_id=community.announcement_group_wa_id,
        )
    return Response(content=out.model_dump_json(by_alias=True), media_type="application/json")


@router.get("/communities/{community_id}/groups", response_model=list[GroupSummaryOut])
def list_community_groups(community_id: uuid.UUID, db: Session = Depends(get_db)) -> list[GroupSummaryOut]:
    community = get_community_or_404(db, community_id)
    groups = db.execute(
        select(Group).where(Group.community_id == community.id).order_by(Group.name)
    ).scalars().all()
    return [
        GroupSummaryOut(
            id=g.id,
            wa_id=g.wa_id,
            name=g.name,
            description=g.description,
            picture_url=g.picture_url,
            is_announcement_group=g.is_announcement_group,
            member_count=g.member_count,
            member_limit=g.member_limit,
            pending_request_count=g.pending_request_count,
            admin_count=get_group_admin_count(db, g.id),
            last_message_at=get_group_last_message_at(db, g.id),
        )
        for g in groups
    ]


@router.get("/communities/{community_id}/members", response_model=list[MemberSummaryOut])
def list_community_members_route(community_id: uuid.UUID, db: Session = Depends(get_db)) -> list[MemberSummaryOut]:
    community = get_community_or_404(db, community_id)
    aggregates = list_community_members(db, community)
    return [
        MemberSummaryOut(
            id=agg.member.id,
            wa_id=agg.member.wa_id,
            display_name=agg.member.display_name,
            avatar_url=agg.member.avatar_url,
            phone_number_masked=agg.member.phone_number_masked,
            is_admin=agg.is_admin,
            is_community_admin=agg.is_community_admin,
            group_count=agg.group_count,
            joined_at=agg.joined_at,
            last_message_at=agg.last_message_at,
            last_seen_at=agg.last_seen_at,
            last_activity_type=agg.last_activity_type,
            last_activity_at=agg.last_activity_at,
            last_activity_content=agg.last_activity_content,
        )
        for agg in sorted(aggregates, key=lambda a: a.member.display_name)
    ]


@router.get("/communities/{community_id}/history", response_model=list[CommunityHistoryPointOut])
def get_community_history_route(
    community_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[CommunityHistoryPointOut]:
    """The community's growth time series, one point per past sync, oldest
    first — the resolution of this history is exactly the sync frequency."""
    get_community_or_404(db, community_id)
    return [CommunityHistoryPointOut.model_validate(s) for s in get_community_history(db, community_id)]


@router.get("/communities/{community_id}/groups/history", response_model=list[GroupHistorySeriesOut])
def get_group_history_route(
    community_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[GroupHistorySeriesOut]:
    """Every group's growth time series in one response, so the frontend can
    build a per-group comparison chart without issuing N requests."""
    get_community_or_404(db, community_id)
    return [
        GroupHistorySeriesOut(
            group_id=series.group_id,
            group_name=series.group_name,
            snapshots=[GroupHistoryPointOut.model_validate(s) for s in series.snapshots],
        )
        for series in get_group_history_for_community(db, community_id)
    ]
