"""Moderation-item dismissal state: "acknowledge this and stop showing it to
me until it gets worse again."

The moderation queue itself (`moderation/service.py`) is otherwise fully
computed live, never stored — this is the one deliberate exception, mirroring
how `models/renewal.py`'s `RenewalCampaign`/`RenewalConfirmation` store real
state instead of only computing live. A row here doesn't hide an item
forever: `moderation/service.py` re-derives the current metric for the
dismissed target on every read and un-suppresses it once that metric is
worse than `metric_snapshot` (the value captured at dismissal time).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from communeer.models.base import Base, uuid_pk


class ModerationDismissal(Base):
    __tablename__ = "moderation_dismissals"
    __table_args__ = (
        UniqueConstraint("community_id", "section", "target_id", name="uq_moderation_dismissal"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    community_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # One of `ModerationQueueData`'s four section names
    # ("admin_coverage_gaps"/"never_active_members"/"join_bursts"/
    # "capacity_attention") — a plain `String`, not a DB enum, since this is
    # an internal categorical tag rather than user-facing data.
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    # The dismissed group/member id, normalized to `str` at write time (see
    # `moderation/service.py`) so lookups are simple string equality
    # regardless of the target's actual id type.
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Whatever numeric value(s) mattered for this section at dismissal time
    # (e.g. {"adminCount": 1}), re-derived server-side rather than trusted
    # from the client — compared against the current value on every queue
    # read to decide whether the item has gotten worse since dismissal.
    metric_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Same nullable-FK-to-users pattern as `AuditEvent.actor_user_id`/
    # `RenewalCampaign.created_by_user_id`: kept even if that user is later
    # deactivated/removed (SET NULL, not CASCADE).
    dismissed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
