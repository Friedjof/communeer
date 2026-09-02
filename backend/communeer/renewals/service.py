"""Renewal-campaign tracking: a mostly-automated membership reconfirmation
process, scoped to a single group — a member can belong to several groups in
the same community, and a renewal round only ever concerns their standing in
one of them, so removal (see `process_due_removals`) never reaches outside
that one group.

Starting a campaign sends a bilingual (German/English) reminder message
directly to each selected member's personal WhatsApp chat, explaining that
reacting 👍 means "I want to stay" and ❌ means "no longer interested" — a
reply is also accepted, but only a reaction is machine-readable, so a plain
text reply still needs a human admin to read it and mark the member
confirmed manually. The two reactions are read automatically via
`apply_renewal_confirm_reaction()`/`apply_renewal_decline_reaction()` (both
called from `webhooks/router.py`): 👍 flips `status` to `confirmed` exactly
like a manual "Mark confirmed" click would; ❌ sets `declined_at`, making the
confirmation behave exactly like an expired one everywhere
`is_confirmation_expired()` is checked — without touching the shared
campaign deadline. Reacting 👍 after an earlier ❌ un-declines (people can
change their mind); the reverse is not special-cased — once truly
`confirmed`, a later ❌ is a no-op, matching `send_renewal_reminder`'s own
"already responded" guard. Anyone still `pending` (or declined) once
`campaign.deadline` passes shows up in the non-responders queue for the
admin to review.

**Removal is manual, on purpose.** Neither a ❌ reaction nor the deadline
passing removes anyone from the group by itself — there is no background job
in this codebase to notice a deadline has quietly passed (see
`communeer.models.renewal` for why "expired" is computed at read time
instead of stored), and reacting is deliberately not wired to an immediate
webhook-triggered removal either, so that an admin always has a chance to
review before anyone is actually kicked. `process_due_removals()` is the one
function that ever calls `remove_group_member()` — an admin clicks a button,
it processes everyone currently declined-or-expired in one batch.

Sending is best-effort per member: a provider failure for one member (see
`providers/whatsapp/base.py`'s raise-on-failure contract for write methods)
never aborts creating the rest of the campaign — it just leaves that one
confirmation's `reminder_sent_at` unset, which the frontend surfaces as a
retryable "not sent" state.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from communeer.errors import (
    ApiError,
    bad_request,
    conflict,
    not_found,
    service_unavailable,
)
from communeer.groups.service import remove_group_member
from communeer.models import AuditEvent, Group, GroupMembership, MembershipStatus
from communeer.models.renewal import (
    RenewalCampaign,
    RenewalConfirmation,
    RenewalConfirmationStatus,
)
from communeer.providers.whatsapp.base import (
    WhatsAppNotConnectedError,
    WhatsAppProvider,
    WhatsAppProviderUnavailableError,
)

DEFAULT_DEADLINE_DAYS = 7

# Reactions read automatically off a reminder message. A reaction *removal*
# comes through as an empty `reactionText` and is deliberately ignored (not
# treated as "undo").
RENEWAL_CONFIRM_REACTION = "👍"
RENEWAL_DECLINE_REACTION = "❌"


def build_renewal_reminder_message(group_name: str, deadline: datetime) -> str:
    """The bilingual (German first, then English) reminder DM sent to each
    member when a renewal round starts or a reminder is resent. Explains the
    fastest path (react 👍 or ❌) up front; a text reply also works but needs
    a human admin to read and act on it. Names the specific group, not the
    community — a renewal round only ever concerns one group."""
    deadline_str = deadline.strftime("%d.%m.%Y")
    return (
        f"Hallo! 👋 Wir prüfen gerade, wer in *{group_name}* weiterhin dabei sein möchte.\n"
        f"Reagiere mit 👍 auf diese Nachricht, wenn du weiterhin dabei sein möchtest, oder mit ❌, "
        f"wenn nicht mehr — bis spätestens {deadline_str}. Eine Antwort auf diese Nachricht geht "
        f"auch, das dauert dann aber etwas länger.\n"
        f"Falls wir nichts von dir hören, wird deine Mitgliedschaft überprüft.\n"
        f"\n—\n\n"
        f"Hi! 👋 We're checking in on who'd like to stay part of *{group_name}*.\n"
        f"React 👍 to this message if you'd like to stay, or ❌ if not — by {deadline_str} at the "
        f"latest. Replying works too, it'll just take a bit longer.\n"
        f"If we don't hear from you, your membership will be reviewed."
    )


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
    """Expiry is *computed*, never stored: `pending` and (past the deadline
    OR declined via a ❌ reaction — a decline is immediate, it doesn't wait
    for `campaign.deadline` to actually pass)."""
    if confirmation.status != RenewalConfirmationStatus.pending:
        return False
    if confirmation.declined_at is not None:
        return True
    now = now if now is not None else datetime.now(UTC)
    return now > _ensure_utc(campaign.deadline)


def get_renewal_suggestions(db: Session, group: Group) -> list[GroupMembership]:
    """Renewal-round candidates: every `member`-status membership of `group`
    that isn't a group admin (or super admin), sorted so the most likely
    renewal candidates surface first. Every field a caller needs
    (`last_message_at`, `joined_at`, etc.) already lives directly on
    `GroupMembership` — no cross-group aggregation needed once a campaign is
    scoped to one group.

    Sort key, in order: (1) members who have **never posted**
    (`last_message_at is None`) first — a real "never active" signal is the
    strongest renewal-candidate indicator now available, so it must not get
    buried; (2) among the rest, longest-since-last-message first (oldest
    `last_message_at` first); (3) as a tie-breaker/fallback, the previous
    behavior is preserved — oldest `joined_at` first, with an unknown
    `joined_at` sorting last rather than first, so missing data never jumps
    the queue.
    """
    memberships = list(
        db.execute(
            select(GroupMembership)
            .options(selectinload(GroupMembership.member))
            .where(GroupMembership.group_id == group.id, GroupMembership.status == MembershipStatus.member)
        ).scalars()
    )
    eligible = [m for m in memberships if not m.is_admin and not m.is_super_admin]
    return sorted(
        eligible,
        key=lambda m: (
            m.last_message_at is not None,
            m.last_message_at,
            m.joined_at is None,
            m.joined_at,
        ),
    )


def create_renewal_campaign(
    db: Session,
    provider: WhatsAppProvider,
    group: Group,
    member_ids: list[uuid.UUID],
    deadline_days: int = DEFAULT_DEADLINE_DAYS,
    actor_user_id: uuid.UUID | None = None,
) -> RenewalCampaign:
    """Create a campaign + one `pending` confirmation per member, sending each
    of them the bilingual reminder DM (see `build_renewal_reminder_message`).

    Every `member_id` must be an actual `member`-status membership of `group`
    and must not be a group admin/super admin — enforced here server-side
    (never just trusted from a frontend's preview step), rejecting the
    *whole* request with `bad_request()` if any selected member fails either
    check.

    Sending is best-effort per member (see module docstring) — a provider
    failure for one member never aborts creating the campaign or the other
    members' confirmations.
    """
    if not member_ids:
        raise bad_request("At least one member must be selected.")

    # de-dupe while preserving order: a repeated id in the request must not
    # trip the (campaign_id, member_id) unique constraint below.
    unique_member_ids = list(dict.fromkeys(member_ids))

    memberships_by_member_id = {
        m.member_id: m
        for m in db.execute(
            select(GroupMembership)
            .options(selectinload(GroupMembership.member))
            .where(GroupMembership.group_id == group.id, GroupMembership.status == MembershipStatus.member)
        ).scalars()
    }
    for member_id in unique_member_ids:
        membership = memberships_by_member_id.get(member_id)
        if membership is None:
            raise bad_request(f"Member {member_id} is not a member of this group.")
        if membership.is_admin or membership.is_super_admin:
            raise bad_request(
                f"Member {member_id} is an admin and cannot be included in a renewal campaign."
            )

    now = datetime.now(UTC)
    campaign = RenewalCampaign(
        group_id=group.id,
        started_at=now,
        deadline=now + timedelta(days=deadline_days),
        created_by_user_id=actor_user_id,
    )
    db.add(campaign)
    db.flush()  # ensure campaign.id exists for the confirmations' FK below

    message = build_renewal_reminder_message(group.name, campaign.deadline)
    reminder_failures = 0
    for member_id in unique_member_ids:
        confirmation = RenewalConfirmation(
            campaign_id=campaign.id,
            member_id=member_id,
            status=RenewalConfirmationStatus.pending,
        )
        member_wa_id = memberships_by_member_id[member_id].member.wa_id
        try:
            confirmation.reminder_message_id = provider.send_text_message(member_wa_id, message)
            confirmation.reminder_sent_at = now
        except (WhatsAppNotConnectedError, WhatsAppProviderUnavailableError):
            reminder_failures += 1
        db.add(confirmation)

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.started",
            target_type="group",
            target_id=str(group.id),
            detail={
                "campaignId": str(campaign.id),
                "memberCount": len(unique_member_ids),
                "deadline": campaign.deadline.isoformat(),
                "reminderFailures": reminder_failures,
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


def send_renewal_reminder(
    db: Session,
    provider: WhatsAppProvider,
    confirmation: RenewalConfirmation,
    campaign: RenewalCampaign,
    actor_user_id: uuid.UUID | None = None,
) -> RenewalConfirmation:
    """(Re)send the reminder DM for one confirmation — used both for a
    member whose initial send failed (see `create_renewal_campaign`) and to
    nudge someone again before the deadline."""
    if confirmation.status != RenewalConfirmationStatus.pending or confirmation.declined_at is not None:
        raise conflict("This member has already responded — no reminder needed.")

    message = build_renewal_reminder_message(campaign.group.name, campaign.deadline)
    try:
        message_id = provider.send_text_message(confirmation.member.wa_id, message)
    except (WhatsAppNotConnectedError, WhatsAppProviderUnavailableError) as exc:
        raise service_unavailable(
            "Could not reach WhatsApp to send the reminder. Please try again shortly."
        ) from exc

    confirmation.reminder_sent_at = datetime.now(UTC)
    confirmation.reminder_message_id = message_id

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.reminder_sent",
            target_type="member",
            target_id=str(confirmation.member_id),
            detail={"campaignId": str(confirmation.campaign_id)},
        )
    )

    db.commit()
    db.refresh(confirmation)
    return confirmation


def apply_renewal_decline_reaction(
    db: Session, message_id: str, actor_user_id: uuid.UUID | None = None
) -> bool:
    """Called from `webhooks/router.py` when a ❌ reaction arrives (no
    `actor_user_id` there — it's a WhatsApp event, not an admin action) and
    from `check_renewal_reactions`'s manual pull below (which does pass the
    admin who clicked "Check reactions"). Looks up the still-`pending`
    confirmation whose reminder this message id belongs to; returns `False`
    (a pure no-op) if none matches, so the webhook can fall back to its
    normal group-activity handling for a reaction that has nothing to do
    with a renewal."""
    confirmation = db.execute(
        select(RenewalConfirmation).where(
            RenewalConfirmation.reminder_message_id == message_id,
            RenewalConfirmation.status == RenewalConfirmationStatus.pending,
        )
    ).scalar_one_or_none()
    if confirmation is None:
        return False

    confirmation.declined_at = datetime.now(UTC)
    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.declined_via_reaction",
            target_type="member",
            target_id=str(confirmation.member_id),
            detail={"campaignId": str(confirmation.campaign_id)},
        )
    )
    db.commit()
    return True


def apply_renewal_confirm_reaction(
    db: Session, message_id: str, actor_user_id: uuid.UUID | None = None
) -> bool:
    """Called from `webhooks/router.py` when a 👍 reaction arrives (no
    `actor_user_id`, same reasoning as `apply_renewal_decline_reaction`) and
    from `check_renewal_reactions`'s manual pull below. Same lookup/no-op
    contract as `apply_renewal_decline_reaction`. Clears an earlier
    `declined_at` too — reacting 👍 after an earlier ❌ is read as "changed
    my mind", not ignored."""
    confirmation = db.execute(
        select(RenewalConfirmation).where(
            RenewalConfirmation.reminder_message_id == message_id,
            RenewalConfirmation.status == RenewalConfirmationStatus.pending,
        )
    ).scalar_one_or_none()
    if confirmation is None:
        return False

    confirmation.status = RenewalConfirmationStatus.confirmed
    confirmation.responded_at = datetime.now(UTC)
    confirmation.declined_at = None
    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.confirmed_via_reaction",
            target_type="member",
            target_id=str(confirmation.member_id),
            detail={"campaignId": str(confirmation.campaign_id)},
        )
    )
    db.commit()
    return True


def remove_from_campaign(
    db: Session, confirmation: RenewalConfirmation, actor_user_id: uuid.UUID | None = None
) -> None:
    """Removes one member's confirmation row from a campaign entirely — for
    "added them by mistake" or "don't need to track this person anymore",
    distinct from confirming/declining. Nothing WhatsApp-side happens here
    (no message is un-sent); this only stops tracking them in Communeer."""
    campaign_id = confirmation.campaign_id
    member_id = confirmation.member_id
    db.delete(confirmation)
    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.removed_from_campaign",
            target_type="member",
            target_id=str(member_id),
            detail={"campaignId": str(campaign_id)},
        )
    )
    db.commit()


def archive_campaign(
    db: Session, campaign: RenewalCampaign, actor_user_id: uuid.UUID | None = None
) -> RenewalCampaign:
    """Marks a campaign archived — a manual step, never automatic even when a
    campaign has zero remaining confirmations (see module docstring). Only
    an archived campaign can be deleted, via `delete_campaign`."""
    if campaign.archived_at is not None:
        raise conflict("This campaign is already archived.")

    campaign.archived_at = datetime.now(UTC)
    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.campaign_archived",
            target_type="group",
            target_id=str(campaign.group_id),
            detail={"campaignId": str(campaign.id)},
        )
    )
    db.commit()
    db.refresh(campaign)
    return campaign


def unarchive_campaign(
    db: Session, campaign: RenewalCampaign, actor_user_id: uuid.UUID | None = None
) -> RenewalCampaign:
    """Reverses `archive_campaign` — restores a campaign to the default view."""
    if campaign.archived_at is None:
        raise conflict("This campaign is not archived.")

    campaign.archived_at = None
    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.campaign_unarchived",
            target_type="group",
            target_id=str(campaign.group_id),
            detail={"campaignId": str(campaign.id)},
        )
    )
    db.commit()
    db.refresh(campaign)
    return campaign


def delete_campaign(db: Session, campaign: RenewalCampaign, actor_user_id: uuid.UUID | None = None) -> None:
    """Hard-deletes a campaign and, via `ondelete="CASCADE"`, its
    confirmations. Guarded behind archiving first — deleting a still-active
    campaign is very likely a mistake (it silently stops tracking every
    member still mid-renewal), so archiving is a required, deliberate first
    step. The audit event is written before the delete so the campaign id
    stays in the log as a plain string reference, same as everywhere else in
    this codebase that logs against a row it's about to remove."""
    if campaign.archived_at is None:
        raise conflict("Archive this campaign before deleting it.")

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="renewal.campaign_deleted",
            target_type="group",
            target_id=str(campaign.group_id),
            detail={"campaignId": str(campaign.id)},
        )
    )
    db.delete(campaign)
    db.commit()


def check_renewal_reactions(
    db: Session, provider: WhatsAppProvider, campaign: RenewalCampaign, actor_user_id: uuid.UUID | None = None
) -> int:
    """Pull-based counterpart to the webhook: actively asks the provider
    what reaction (if any) currently sits on each still-`pending`,
    already-sent confirmation's reminder message, and applies the same
    confirm/decline logic the webhook would — for when a caller wants an
    answer right now rather than waiting on (or trusting) the webhook.

    Best-effort per confirmation, matching `create_renewal_campaign`'s
    posture: a provider failure for one member is logged into the summary
    count below but never aborts checking the rest. Returns how many
    confirmations were actually updated (confirmed or declined) by this
    call."""
    # Materialized up front, not lazily iterated: `apply_renewal_*_reaction`
    # below each commit mid-loop, which shouldn't be interleaved with an
    # still-open result cursor.
    confirmations = list(
        db.execute(
            select(RenewalConfirmation)
            .options(selectinload(RenewalConfirmation.member))
            .where(
                RenewalConfirmation.campaign_id == campaign.id,
                RenewalConfirmation.status == RenewalConfirmationStatus.pending,
                # Excludes an already-declined confirmation too: declining
                # doesn't flip `status` away from `pending` (see
                # `is_confirmation_expired`'s docstring), so without this a
                # repeat check would keep "re-declining" (and re-counting)
                # the same confirmation on every call — the same
                # already-responded guard `send_renewal_reminder` uses.
                RenewalConfirmation.declined_at.is_(None),
                RenewalConfirmation.reminder_message_id.is_not(None),
            )
        ).scalars()
    )

    updated = 0
    for confirmation in confirmations:
        try:
            reaction = provider.get_reaction_for_message(confirmation.member.wa_id, confirmation.reminder_message_id)
        except (WhatsAppNotConnectedError, WhatsAppProviderUnavailableError):
            continue

        if reaction == RENEWAL_CONFIRM_REACTION:
            if apply_renewal_confirm_reaction(db, confirmation.reminder_message_id, actor_user_id):
                updated += 1
        elif reaction == RENEWAL_DECLINE_REACTION and apply_renewal_decline_reaction(
            db, confirmation.reminder_message_id, actor_user_id
        ):
            updated += 1

    return updated


def process_due_removals(
    db: Session, provider: WhatsAppProvider, campaign: RenewalCampaign, actor_user_id: uuid.UUID | None = None
) -> int:
    """Manually-triggered batch removal — the only place this module ever
    removes anyone from WhatsApp (see module docstring: no reaction or
    deadline ever removes someone by itself). An admin clicks a button, and
    every confirmation currently `is_confirmation_expired()` (declined via ❌,
    or past the deadline with no response) that hasn't already been
    processed gets removed from `campaign.group` via `remove_group_member()`
    — the same provider-call + membership-delete + counter-recompute +
    audit-event helper the Members-tab "Remove" action uses.

    Best-effort per confirmation, matching this module's usual posture: an
    `ApiError` for one member (typically `service_unavailable` from a
    provider hiccup) never aborts the rest of the batch — that confirmation
    is simply left for a retry on the next click. A membership that's
    already gone by some other path (e.g. removed manually in the Members
    tab) is treated as already-done rather than an error. Returns how many
    members were actually removed by this call."""
    confirmations = list(
        db.execute(
            select(RenewalConfirmation)
            .options(selectinload(RenewalConfirmation.member))
            .where(
                RenewalConfirmation.campaign_id == campaign.id,
                RenewalConfirmation.status == RenewalConfirmationStatus.pending,
                RenewalConfirmation.removed_at.is_(None),
            )
        ).scalars()
    )

    now = datetime.now(UTC)
    removed = 0
    for confirmation in confirmations:
        if not is_confirmation_expired(confirmation, campaign, now=now):
            continue

        membership_exists = db.execute(
            select(GroupMembership.id).where(
                GroupMembership.group_id == campaign.group_id,
                GroupMembership.member_id == confirmation.member_id,
            )
        ).scalar_one_or_none()

        if membership_exists is not None:
            try:
                remove_group_member(db, provider, campaign.group, confirmation.member_id, actor_user_id)
            except ApiError as exc:
                if exc.status_code != 404:
                    continue  # provider failure — leave for a retry on the next click

        confirmation.removed_at = now
        db.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                action="renewal.member_removed",
                target_type="member",
                target_id=str(confirmation.member_id),
                detail={"campaignId": str(campaign.id)},
            )
        )
        db.commit()
        removed += 1

    return removed


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


def get_campaign_summaries(
    db: Session, campaigns: list[RenewalCampaign]
) -> dict[uuid.UUID, CampaignCounts]:
    """Same pending/confirmed/expired/total computation as
    `get_campaign_summary()`, batched across many campaigns in a single query
    instead of one `get_campaign_confirmations()` round trip per campaign —
    used by the campaign-listing endpoint. A campaign with zero confirmations
    still gets an all-zero `CampaignCounts` entry (never a missing key)."""
    campaign_ids = [campaign.id for campaign in campaigns]
    confirmations_by_campaign: dict[uuid.UUID, list[RenewalConfirmation]] = {
        campaign_id: [] for campaign_id in campaign_ids
    }
    if campaign_ids:
        rows = db.execute(
            select(RenewalConfirmation).where(RenewalConfirmation.campaign_id.in_(campaign_ids))
        ).scalars()
        for confirmation in rows:
            confirmations_by_campaign[confirmation.campaign_id].append(confirmation)

    now = datetime.now(UTC)
    campaigns_by_id = {campaign.id: campaign for campaign in campaigns}
    summaries: dict[uuid.UUID, CampaignCounts] = {}
    for campaign_id, confirmations in confirmations_by_campaign.items():
        campaign = campaigns_by_id[campaign_id]
        pending = confirmed = expired = 0
        for confirmation in confirmations:
            if confirmation.status == RenewalConfirmationStatus.confirmed:
                confirmed += 1
            elif is_confirmation_expired(confirmation, campaign, now=now):
                expired += 1
            else:
                pending += 1
        summaries[campaign_id] = CampaignCounts(
            pending=pending, confirmed=confirmed, expired=expired, total=len(confirmations)
        )
    return summaries


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


def list_campaigns_for_group(db: Session, group_id: uuid.UUID) -> list[RenewalCampaign]:
    """Campaigns for a group, most recently started first."""
    return list(
        db.execute(
            select(RenewalCampaign)
            .where(RenewalCampaign.group_id == group_id)
            .order_by(RenewalCampaign.started_at.desc())
        ).scalars()
    )


def get_campaign_or_404(db: Session, campaign_id: uuid.UUID) -> RenewalCampaign:
    campaign = db.get(RenewalCampaign, campaign_id)
    if campaign is None:
        raise not_found("Renewal campaign not found.")
    return campaign
