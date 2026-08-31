"""Renewal-campaign tracking for a human-run membership renewal process.

`RenewalCampaign` groups one "please reconfirm your membership" round for a
single group (not a whole community — a member can be in several groups of
the same community, and a renewal round only ever concerns their standing in
one of them); `RenewalConfirmation` is one row per invited member.

**"expired" is deliberately not a stored status.** This codebase has no
scheduled/background job infrastructure (Dramatiq/Redis are provisioned in
`docker-compose.yml` but explicitly unused everywhere else), and everything
else here computes derived state at read time instead of needing a cron job
to flip a flag (see `models/membership.py`'s docstring on why
`CommunityMembership` isn't a stored table either, and `models/snapshot.py`
for the same "no background job" reasoning applied elsewhere). A confirmation
is expired if and only if `status == pending` and
`now() > campaign.deadline` — computed in `renewals/service.py`, never
written back as a third enum value that something would need to actively
transition.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from communeer.models.base import Base, uuid_pk


class RenewalConfirmationStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"


class RenewalCampaign(Base):
    __tablename__ = "renewal_campaigns"

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group: Mapped["Group"] = relationship()  # noqa: F821
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    # Computed by the caller as `started_at + N days` (default N=7) — stored
    # rather than re-derived so a campaign's deadline is fixed at creation
    # time even if the default policy changes later.
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Same nullable-FK-to-users pattern as `AuditEvent.actor_user_id`: the
    # admin who started the campaign, kept even if that user is later
    # deactivated/removed (SET NULL, not CASCADE).
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Set when an admin archives the campaign — a manual, human-driven action
    # (see module docstring's "no background job" convention), never set
    # automatically even when a campaign has zero remaining confirmations.
    # `delete_campaign` refuses to run while this is `None`, so archiving is
    # always the first step toward deleting a campaign.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RenewalConfirmation(Base):
    __tablename__ = "renewal_confirmations"
    __table_args__ = (UniqueConstraint("campaign_id", "member_id", name="uq_renewal_confirmation"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("renewal_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[RenewalConfirmationStatus] = mapped_column(
        Enum(RenewalConfirmationStatus, native_enum=False, length=16),
        nullable=False,
        default=RenewalConfirmationStatus.pending,
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set once `send_text_message` succeeds for this confirmation (on
    # campaign creation or a manual resend) — `None` means the reminder
    # either hasn't been attempted yet or the attempt failed, both of which
    # the frontend surfaces as "not sent" with a retry action.
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The provider's message id for the sent reminder, used to correlate an
    # inbound ❌ reaction (see `webhooks/router.py`) back to this exact
    # confirmation. `None` when the provider couldn't supply one.
    reminder_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Set when the member reacts ❌ to the reminder — an explicit "no longer
    # interested" signal, treated identically to a missed deadline by
    # `is_confirmation_expired()` without touching the shared campaign
    # deadline.
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set once `process_due_removals` has actually removed this member from
    # the campaign's group (via the WhatsApp provider) — a manual, admin-
    # triggered batch action (see `renewals/service.py`), never automatic.
    # Doubles as an idempotency guard: a confirmation with this set is
    # skipped on the next run instead of being removed a second time.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # One-directional (no `back_populates` on `Member`, mirroring how
    # `AuditEvent`/`GroupMembership` reach across FKs elsewhere in this
    # codebase) — exists purely so the renewals router can render
    # `displayName`/`waId` without a second query per row.
    member: Mapped["Member"] = relationship()  # noqa: F821
