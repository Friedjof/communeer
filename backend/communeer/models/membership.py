import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from communeer.models.base import Base, uuid_pk


class MembershipStatus(str, enum.Enum):
    member = "member"
    pending = "pending"


class ActivityType(str, enum.Enum):
    """What kind of signal `last_activity_at`/`last_activity_content` last
    captured. `view` is deliberately kept in this enum even though nothing
    ever populates it (see `webhooks/router.py`'s module docstring): WhatsApp
    exposes no read-receipt event for messages from other people, so this is
    an honest "structurally supported, never actually observed" member, the
    same posture already established for `last_seen_at` on this model."""

    message = "message"
    reaction = "reaction"
    view = "view"


class GroupMembership(Base):
    """A member's status within a single WhatsApp group.

    `CommunityMembership` is intentionally *not* a stored table: a member's
    community-level membership and community-admin status are fully derived
    from these rows (community-admin = admin of the community's announcement
    group), computed as a query in `communities/service.py` instead of a
    second table that could drift out of sync on every provider sync.
    """

    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("group_id", "member_id", name="uq_group_membership"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(MembershipStatus, native_enum=False, length=16), nullable=False, default=MembershipStatus.member
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Real, provider-observed activity signals — see `providers/whatsapp/base.py`'s
    # `ProviderMembership` and `sync/service.py`'s "set once / advance forward
    # only, never regress or blank" stamping logic for how these get filled in.
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Unified "last activity" signal (message/reaction/view), populated
    # live by `webhooks/router.py` — see that module for why this is
    # deliberately NOT filled in by `sync_community` (no cheap bulk way to
    # fetch reactions, and messages are already covered by
    # `last_message_at` above). Same "set once / advance forward only,
    # never regress or blank" stamping discipline as `last_message_at`.
    last_activity_type: Mapped[ActivityType | None] = mapped_column(
        Enum(ActivityType, native_enum=False, length=16), nullable=True
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    group: Mapped["Group"] = relationship(back_populates="memberships")  # noqa: F821
    member: Mapped["Member"] = relationship(back_populates="memberships")  # noqa: F821
