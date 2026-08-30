import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.communities.router import get_community_or_404
from communeer.deps import get_current_user, get_db, require_role
from communeer.errors import not_found
from communeer.models import User, UserRole
from communeer.models.renewal import RenewalCampaign, RenewalConfirmation
from communeer.renewals.schemas import (
    CreateRenewalCampaignIn,
    RenewalCampaignDetailOut,
    RenewalCampaignSummaryOut,
    RenewalConfirmationOut,
    RenewalSuggestionOut,
)
from communeer.renewals.service import (
    CampaignCounts,
    confirm_renewal,
    create_renewal_campaign,
    get_campaign_confirmations,
    get_campaign_or_404,
    get_campaign_summaries,
    get_campaign_summary,
    get_non_responders,
    get_renewal_suggestions,
    is_confirmation_expired,
    list_campaigns_for_community,
)

router = APIRouter(tags=["renewals"], dependencies=[Depends(get_current_user)])


def _campaign_summary_out_from_counts(campaign: RenewalCampaign, counts: CampaignCounts) -> RenewalCampaignSummaryOut:
    return RenewalCampaignSummaryOut(
        id=campaign.id,
        community_id=campaign.community_id,
        started_at=campaign.started_at,
        deadline=campaign.deadline,
        pending_count=counts.pending,
        confirmed_count=counts.confirmed,
        expired_count=counts.expired,
        total_count=counts.total,
    )


def _campaign_summary_out(db: Session, campaign: RenewalCampaign) -> RenewalCampaignSummaryOut:
    counts = get_campaign_summary(db, campaign)
    return _campaign_summary_out_from_counts(campaign, counts)


def _confirmation_out(confirmation: RenewalConfirmation, campaign: RenewalCampaign) -> RenewalConfirmationOut:
    return RenewalConfirmationOut(
        member_id=confirmation.member_id,
        wa_id=confirmation.member.wa_id,
        display_name=confirmation.member.display_name,
        status=confirmation.status,
        is_expired=is_confirmation_expired(confirmation, campaign),
        responded_at=confirmation.responded_at,
    )


@router.get(
    "/communities/{community_id}/renewals/suggestions",
    response_model=list[RenewalSuggestionOut],
)
def get_renewal_suggestions_route(
    community_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[RenewalSuggestionOut]:
    community = get_community_or_404(db, community_id)
    return [
        RenewalSuggestionOut(
            member_id=agg.member.id,
            wa_id=agg.member.wa_id,
            display_name=agg.member.display_name,
            avatar_url=agg.member.avatar_url,
            phone_number_masked=agg.member.phone_number_masked,
            group_count=agg.group_count,
            joined_at=agg.joined_at,
            last_message_at=agg.last_message_at,
            last_seen_at=agg.last_seen_at,
            last_activity_type=agg.last_activity_type,
            last_activity_at=agg.last_activity_at,
            last_activity_content=agg.last_activity_content,
        )
        for agg in get_renewal_suggestions(db, community)
    ]


@router.post(
    "/communities/{community_id}/renewals",
    response_model=RenewalCampaignSummaryOut,
    dependencies=[Depends(require_role(UserRole.owner, UserRole.admin))],
)
def create_renewal_campaign_route(
    community_id: uuid.UUID,
    body: CreateRenewalCampaignIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenewalCampaignSummaryOut:
    community = get_community_or_404(db, community_id)
    campaign = create_renewal_campaign(
        db,
        community,
        member_ids=body.member_ids,
        deadline_days=body.deadline_days,
        actor_user_id=user.id,
    )
    return _campaign_summary_out(db, campaign)


@router.get("/communities/{community_id}/renewals", response_model=list[RenewalCampaignSummaryOut])
def list_renewal_campaigns_route(
    community_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[RenewalCampaignSummaryOut]:
    community = get_community_or_404(db, community_id)
    campaigns = list_campaigns_for_community(db, community.id)
    summaries = get_campaign_summaries(db, campaigns)
    return [_campaign_summary_out_from_counts(c, summaries[c.id]) for c in campaigns]


@router.get("/renewals/{campaign_id}", response_model=RenewalCampaignDetailOut)
def get_renewal_campaign_route(campaign_id: uuid.UUID, db: Session = Depends(get_db)) -> RenewalCampaignDetailOut:
    campaign = get_campaign_or_404(db, campaign_id)
    summary = _campaign_summary_out(db, campaign)
    confirmations = get_campaign_confirmations(db, campaign)
    return RenewalCampaignDetailOut(
        **summary.model_dump(),
        confirmations=[_confirmation_out(c, campaign) for c in confirmations],
    )


@router.post(
    "/renewals/{campaign_id}/confirmations/{member_id}/confirm",
    response_model=RenewalConfirmationOut,
    dependencies=[Depends(require_role(UserRole.owner, UserRole.admin))],
)
def confirm_renewal_route(
    campaign_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenewalConfirmationOut:
    campaign = get_campaign_or_404(db, campaign_id)
    confirmation = db.execute(
        select(RenewalConfirmation).where(
            RenewalConfirmation.campaign_id == campaign.id,
            RenewalConfirmation.member_id == member_id,
        )
    ).scalar_one_or_none()
    if confirmation is None:
        raise not_found("Renewal confirmation not found.")

    confirmation = confirm_renewal(db, confirmation, actor_user_id=user.id)
    return _confirmation_out(confirmation, campaign)


@router.get("/renewals/{campaign_id}/non-responders", response_model=list[RenewalConfirmationOut])
def get_non_responders_route(campaign_id: uuid.UUID, db: Session = Depends(get_db)) -> list[RenewalConfirmationOut]:
    campaign = get_campaign_or_404(db, campaign_id)
    return [_confirmation_out(c, campaign) for c in get_non_responders(db, campaign)]
