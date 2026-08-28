"""Renewal-campaign tracking for a human-run membership renewal process.

`RenewalCampaign` groups one "please reconfirm your membership" round for a
community; `RenewalConfirmation` is one row per invited member.

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

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from communeer.models.base import Base, uuid_pk


class RenewalConfirmationStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"


class RenewalCampaign(Base):
    __tablename__ = "renewal_campaigns"

    id: Mapped[uuid.UUID] = uuid_pk()
    community_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
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

    # One-directional (no `back_populates` on `Member`, mirroring how
    # `AuditEvent`/`GroupMembership` reach across FKs elsewhere in this
    # codebase) — exists purely so the renewals router can render
    # `displayName`/`waId` without a second query per row.
    member: Mapped["Member"] = relationship()  # noqa: F821
