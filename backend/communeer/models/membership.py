import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from communeer.models.base import Base, uuid_pk


class MembershipStatus(str, enum.Enum):
    member = "member"
    pending = "pending"


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

    group: Mapped["Group"] = relationship(back_populates="memberships")  # noqa: F821
    member: Mapped["Member"] = relationship(back_populates="memberships")  # noqa: F821
