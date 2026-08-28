"""Renewal-campaign tracking: a human-run membership reconfirmation process.

This is a *tracking* layer only — no message is ever sent and no reaction is
ever read (that capability doesn't exist in this codebase yet, and is
explicitly gated behind a separate approval). An admin starts a campaign for
a hand-picked set of non-admin members, then manually marks people confirmed
as replies come in via WhatsApp itself; anyone still `pending` once
`campaign.deadline` passes shows up in the non-responders queue for the admin
to review before manually removing them in WhatsApp (no `remove_member` here
either).

See `communeer.models.renewal` for why "expired" is computed at read time
instead of stored.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from communeer.communities.service import MemberAggregate, list_community_members
from communeer.errors import bad_request, not_found
from communeer.models import AuditEvent, Community
from communeer.models.renewal import (
    RenewalCampaign,
    RenewalConfirmation,
    RenewalConfirmationStatus,
)

DEFAULT_DEADLINE_DAYS = 7


def _ensure_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip: a `DateTime(timezone=True)` value
    written as UTC-aware comes back naive from a fresh query or `db.refresh`
    (confirmed empirically against this project's SQLite setup). Every
    datetime this module stores is UTC by convention, so a naive value read
    back is re-tagged as UTC rather than compared naively against a
    timezone-aware `datetime.now(UTC)` (which would raise `TypeError`)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def is_confirmation_expired(
    confirmation: RenewalConfirmation, campaign: RenewalCampaign, *, now: datetime | None = None
) -> bool:
    """Expiry is *computed*, never stored: `pending` and past the deadline."""
    if confirmation.status != RenewalConfirmationStatus.pending:
        return False
    now = now if now is not None else datetime.now(UTC)
    return now > _ensure_utc(campaign.deadline)


def get_renewal_suggestions(db: Session, community: Community) -> list[MemberAggregate]:
    """Renewal-round candidates: every community member who is not an admin
    (of any group, or of the community specifically — either is enough to
    exclude), oldest `joined_at` first so the longest-unconfirmed tenure
    surfaces first for a human to review (an unknown `joined_at` sorts last,
    not first, so missing data never jumps the queue).

    This is a suggestion list only — no message/read-receipt activity data
    exists in this codebase yet (that needs a separate, unbuilt verification
    spike). Callers building a response from this must mark every row as
    "activity unknown" explicitly rather than imply data that isn't there.
    """
    aggregates = list_community_members(db, community)
    eligible = [a for a in aggregates if not a.is_admin and not a.is_community_admin]
    return sorted(eligible, key=lambda a: (a.joined_at is None, a.joined_at))


def create_renewal_campaign(
    db: Session,
    community: Community,
    member_ids: list[uuid.UUID],
    deadline_days: int = DEFAULT_DEADLINE_DAYS,
    actor_user_id: uuid.UUID | None = None,
) -> RenewalCampaign:
    """Create a campaign + one `pending` confirmation per member.

    Every `member_id` must be an actual member of `community` and must not be
    an admin — enforced here server-side (never just trusted from a
    frontend's preview step), rejecting the *whole* request with
    `bad_request()` if any selected member fails either check.
    """
    if not member_ids:
        raise bad_request("At least one member must be selected.")

    # de-dupe while preserving order: a repeated id in the request must not
    # trip the (campaign_id, member_id) unique constraint below.
    unique_member_ids = list(dict.fromkeys(member_ids))

    aggregates_by_member_id = {a.member.id: a for a in list_community_members(db, community)}
    for member_id in unique_member_ids:
        aggregate = aggregates_by_member_id.get(member_id)
        if aggregate is None:
            raise bad_request(f"Member {member_id} is not a member of this community.")
        if aggregate.is_admin or aggregate.is_community_admin:
            raise bad_request(
                f"Member {member_id} is an admin and cannot be included in a renewal campaign."
            )

    now = datetime.now(UTC)
    campaign = RenewalCampaign(
        community_id=community.id,
        started_at=now,
        deadline=now + timedelta(days=deadline_days),
        created_by_user_id=actor_user_id,
    )
    db.add(campaign)
    db.flush()  # ensure campaign.id exists for the confirmations' FK below

    for member_id in unique_member_ids:
        db.add(
            RenewalConfirmation(
                campaign_id=campaign.id,
                member_id=member_id,
                status=RenewalConfirmationStatus.pending,
            )
        )

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.started",
            target_type="community",
            target_id=str(community.id),
            detail={
                "campaignId": str(campaign.id),
                "memberCount": len(unique_member_ids),
                "deadline": campaign.deadline.isoformat(),
            },
        )
    )

    db.commit()
    db.refresh(campaign)
    return campaign


def confirm_renewal(
    db: Session, confirmation: RenewalConfirmation, actor_user_id: uuid.UUID | None = None
) -> RenewalConfirmation:
    """Mark one confirmation as confirmed. `status` only ever moves
    pending -> confirmed here — it is never set to anything resembling
    "expired"; that state is always computed (see module docstring)."""
    confirmation.status = RenewalConfirmationStatus.confirmed
    confirmation.responded_at = datetime.now(UTC)

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.confirmed",
            target_type="member",
            target_id=str(confirmation.member_id),
            detail={"campaignId": str(confirmation.campaign_id)},
        )
    )

    db.commit()
    db.refresh(confirmation)
    return confirmation


@dataclass
class CampaignCounts:
    pending: int
    confirmed: int
    expired: int
    total: int


def get_campaign_summary(db: Session, campaign: RenewalCampaign) -> CampaignCounts:
    """Counts of pending / confirmed / expired for a campaign. `expired` is
    computed here at read time, never read off a stored column."""
    confirmations = get_campaign_confirmations(db, campaign)
    now = datetime.now(UTC)

    pending = confirmed = expired = 0
    for confirmation in confirmations:
        if confirmation.status == RenewalConfirmationStatus.confirmed:
            confirmed += 1
        elif is_confirmation_expired(confirmation, campaign, now=now):
            expired += 1
        else:
            pending += 1

    return CampaignCounts(pending=pending, confirmed=confirmed, expired=expired, total=len(confirmations))


def get_campaign_confirmations(db: Session, campaign: RenewalCampaign) -> list[RenewalConfirmation]:
    """Every confirmation row for a campaign, with `member` eager-loaded so a
    caller can render display info without a query per row."""
    return list(
        db.execute(
            select(RenewalConfirmation)
            .options(selectinload(RenewalConfirmation.member))
            .where(RenewalConfirmation.campaign_id == campaign.id)
        ).scalars()
    )


def get_non_responders(db: Session, campaign: RenewalCampaign) -> list[RenewalConfirmation]:
    """The "nobody heard back from these people" review queue: confirmations
    still `pending` once the deadline has passed. Meant for an admin to
    review before manually removing people in WhatsApp itself — nothing here
    writes to WhatsApp or changes `status`."""
    now = datetime.now(UTC)
    return [
        confirmation
        for confirmation in get_campaign_confirmations(db, campaign)
        if is_confirmation_expired(confirmation, campaign, now=now)
    ]


def list_campaigns_for_community(db: Session, community_id: uuid.UUID) -> list[RenewalCampaign]:
    """Campaigns for a community, most recently started first."""
    return list(
        db.execute(
            select(RenewalCampaign)
            .where(RenewalCampaign.community_id == community_id)
            .order_by(RenewalCampaign.started_at.desc())
        ).scalars()
    )


def get_campaign_or_404(db: Session, campaign_id: uuid.UUID) -> RenewalCampaign:
    campaign = db.get(RenewalCampaign, campaign_id)
    if campaign is None:
        raise not_found("Renewal campaign not found.")
    return campaign
