import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.authz import ensure_group_access
from communeer.deps import (
    get_current_user,
    get_db,
    get_provider,
    require_group_access,
    require_role,
)
from communeer.errors import not_found
from communeer.groups.router import get_group_or_404
from communeer.models import User, UserRole
from communeer.models.renewal import RenewalCampaign, RenewalConfirmation
from communeer.providers.whatsapp.base import WhatsAppProvider
from communeer.renewals.schemas import (
    CreateRenewalCampaignIn,
    RenewalCampaignDetailOut,
    RenewalCampaignSummaryOut,
    RenewalConfirmationOut,
    RenewalSuggestionOut,
)
from communeer.renewals.service import (
    CampaignCounts,
    archive_campaign,
    check_renewal_reactions,
    confirm_renewal,
    create_renewal_campaign,
    delete_campaign,
    get_campaign_confirmations,
    get_campaign_or_404,
    get_campaign_summaries,
    get_campaign_summary,
    get_non_responders,
    get_renewal_suggestions,
    is_confirmation_expired,
    list_campaigns_for_group,
    process_due_removals,
    remove_from_campaign,
    send_renewal_reminder,
    unarchive_campaign,
)

router = APIRouter(tags=["renewals"], dependencies=[Depends(get_current_user)])


def _campaign_summary_out_from_counts(campaign: RenewalCampaign, counts: CampaignCounts) -> RenewalCampaignSummaryOut:
    return RenewalCampaignSummaryOut(
        id=campaign.id,
        group_id=campaign.group_id,
        started_at=campaign.started_at,
        deadline=campaign.deadline,
        pending_count=counts.pending,
        confirmed_count=counts.confirmed,
        expired_count=counts.expired,
        total_count=counts.total,
        archived_at=campaign.archived_at,
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
        reminder_sent_at=confirmation.reminder_sent_at,
        declined_at=confirmation.declined_at,
        removed_at=confirmation.removed_at,
    )


def _check_campaign_group_access(
    campaign_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """`campaign_id`-keyed routes carry no `group_id` in their path (unlike
    `groups/*`), so `require_group_access()` can't apply directly here — this
    loads the campaign first and checks `campaign.group_id` instead. The
    resulting extra `get_campaign_or_404` call (the route handler itself
    calls it again) is a cheap, accepted redundancy — same tolerance for
    re-deriving already-fetched data this codebase already has elsewhere
    (e.g. `_group_summary`)."""
    campaign = get_campaign_or_404(db, campaign_id)
    ensure_group_access(db, user, campaign.group_id)
    return user


def _get_confirmation_or_404(db: Session, campaign: RenewalCampaign, member_id: uuid.UUID) -> RenewalConfirmation:
    confirmation = db.execute(
        select(RenewalConfirmation).where(
            RenewalConfirmation.campaign_id == campaign.id,
            RenewalConfirmation.member_id == member_id,
        )
    ).scalar_one_or_none()
    if confirmation is None:
        raise not_found("Renewal confirmation not found.")
    return confirmation


@router.get(
    "/groups/{group_id}/renewals/suggestions",
    response_model=list[RenewalSuggestionOut],
    dependencies=[Depends(require_group_access())],
)
def get_renewal_suggestions_route(group_id: uuid.UUID, db: Session = Depends(get_db)) -> list[RenewalSuggestionOut]:
    group = get_group_or_404(db, group_id)
    return [
        RenewalSuggestionOut(
            member_id=membership.member.id,
            wa_id=membership.member.wa_id,
            display_name=membership.member.display_name,
            avatar_url=membership.member.avatar_url,
            phone_number_masked=membership.member.phone_number_masked,
            joined_at=membership.joined_at,
            last_message_at=membership.last_message_at,
            last_seen_at=membership.last_seen_at,
            last_activity_type=membership.last_activity_type,
            last_activity_at=membership.last_activity_at,
            last_activity_content=membership.last_activity_content,
        )
        for membership in get_renewal_suggestions(db, group)
    ]


@router.post(
    "/groups/{group_id}/renewals",
    response_model=RenewalCampaignSummaryOut,
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(require_group_access()),
    ],
)
def create_renewal_campaign_route(
    group_id: uuid.UUID,
    body: CreateRenewalCampaignIn,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> RenewalCampaignSummaryOut:
    group = get_group_or_404(db, group_id)
    campaign = create_renewal_campaign(
        db,
        provider,
        group,
        member_ids=body.member_ids,
        deadline_days=body.deadline_days,
        actor_user_id=user.id,
    )
    return _campaign_summary_out(db, campaign)


@router.get(
    "/groups/{group_id}/renewals",
    response_model=list[RenewalCampaignSummaryOut],
    dependencies=[Depends(require_group_access())],
)
def list_renewal_campaigns_route(group_id: uuid.UUID, db: Session = Depends(get_db)) -> list[RenewalCampaignSummaryOut]:
    group = get_group_or_404(db, group_id)
    campaigns = list_campaigns_for_group(db, group.id)
    summaries = get_campaign_summaries(db, campaigns)
    return [_campaign_summary_out_from_counts(c, summaries[c.id]) for c in campaigns]


@router.get(
    "/renewals/{campaign_id}",
    response_model=RenewalCampaignDetailOut,
    dependencies=[Depends(_check_campaign_group_access)],
)
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
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(_check_campaign_group_access),
    ],
)
def confirm_renewal_route(
    campaign_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenewalConfirmationOut:
    campaign = get_campaign_or_404(db, campaign_id)
    confirmation = _get_confirmation_or_404(db, campaign, member_id)
    confirmation = confirm_renewal(db, confirmation, actor_user_id=user.id)
    return _confirmation_out(confirmation, campaign)


@router.post(
    "/renewals/{campaign_id}/confirmations/{member_id}/remove",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(_check_campaign_group_access),
    ],
)
def remove_from_campaign_route(
    campaign_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    campaign = get_campaign_or_404(db, campaign_id)
    confirmation = _get_confirmation_or_404(db, campaign, member_id)
    remove_from_campaign(db, confirmation, actor_user_id=user.id)


@router.post(
    "/renewals/{campaign_id}/confirmations/{member_id}/send-reminder",
    response_model=RenewalConfirmationOut,
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(_check_campaign_group_access),
    ],
)
def send_renewal_reminder_route(
    campaign_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> RenewalConfirmationOut:
    campaign = get_campaign_or_404(db, campaign_id)
    confirmation = _get_confirmation_or_404(db, campaign, member_id)
    confirmation = send_renewal_reminder(db, provider, confirmation, campaign, actor_user_id=user.id)
    return _confirmation_out(confirmation, campaign)


@router.post(
    "/renewals/{campaign_id}/check-reactions",
    response_model=RenewalCampaignDetailOut,
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(_check_campaign_group_access),
    ],
)
def check_renewal_reactions_route(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> RenewalCampaignDetailOut:
    """Pull-based check: asks WhatsApp directly what reaction (if any) sits
    on each pending member's reminder right now, applying the same
    confirm/decline effect the webhook would — for when a caller doesn't
    want to wait on (or trust) the webhook. Returns the full, fresh campaign
    detail so the frontend can render the result in one round trip."""
    campaign = get_campaign_or_404(db, campaign_id)
    check_renewal_reactions(db, provider, campaign, actor_user_id=user.id)
    summary = _campaign_summary_out(db, campaign)
    confirmations = get_campaign_confirmations(db, campaign)
    return RenewalCampaignDetailOut(
        **summary.model_dump(),
        confirmations=[_confirmation_out(c, campaign) for c in confirmations],
    )


@router.post(
    "/renewals/{campaign_id}/process-removals",
    response_model=RenewalCampaignDetailOut,
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(_check_campaign_group_access),
    ],
)
def process_due_removals_route(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> RenewalCampaignDetailOut:
    """Removes everyone currently declined-or-expired in this campaign from
    its group, in one batch (see `process_due_removals`'s docstring — this is
    the only place a renewal campaign ever removes someone). Returns the
    full, fresh campaign detail so the frontend can render the result in one
    round trip."""
    campaign = get_campaign_or_404(db, campaign_id)
    process_due_removals(db, provider, campaign, actor_user_id=user.id)
    summary = _campaign_summary_out(db, campaign)
    confirmations = get_campaign_confirmations(db, campaign)
    return RenewalCampaignDetailOut(
        **summary.model_dump(),
        confirmations=[_confirmation_out(c, campaign) for c in confirmations],
    )


@router.get(
    "/renewals/{campaign_id}/non-responders",
    response_model=list[RenewalConfirmationOut],
    dependencies=[Depends(_check_campaign_group_access)],
)
def get_non_responders_route(campaign_id: uuid.UUID, db: Session = Depends(get_db)) -> list[RenewalConfirmationOut]:
    campaign = get_campaign_or_404(db, campaign_id)
    return [_confirmation_out(c, campaign) for c in get_non_responders(db, campaign)]


@router.post(
    "/renewals/{campaign_id}/archive",
    response_model=RenewalCampaignSummaryOut,
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(_check_campaign_group_access),
    ],
)
def archive_campaign_route(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenewalCampaignSummaryOut:
    campaign = get_campaign_or_404(db, campaign_id)
    campaign = archive_campaign(db, campaign, actor_user_id=user.id)
    return _campaign_summary_out(db, campaign)


@router.post(
    "/renewals/{campaign_id}/unarchive",
    response_model=RenewalCampaignSummaryOut,
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(_check_campaign_group_access),
    ],
)
def unarchive_campaign_route(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenewalCampaignSummaryOut:
    campaign = get_campaign_or_404(db, campaign_id)
    campaign = unarchive_campaign(db, campaign, actor_user_id=user.id)
    return _campaign_summary_out(db, campaign)


@router.delete(
    "/renewals/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(_check_campaign_group_access),
    ],
)
def delete_campaign_route(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    campaign = get_campaign_or_404(db, campaign_id)
    delete_campaign(db, campaign, actor_user_id=user.id)
