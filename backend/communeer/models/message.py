"""Persisted history of inbound WhatsApp group messages.

Additive to `GroupMembership.last_activity_content` (`models/membership.py`),
not a replacement: that field stays as a cheap, single-slot "latest activity"
cache used by list/aggregate views, while this table is the actual,
unbounded, queryable history — needed for the message-log tab
(`groups/service.py::list_group_messages`) and for moderation signals that
need more than "what was the last thing this member said"
(`moderation/service.py`'s `message_bursts`/`duplicate_content` sections).

No media blob storage: `content` holds the caption/body text for a media
message, or a synthesized placeholder if it has neither — see
`webhooks/router.py::_handle_onmessage`.

Retention is deliberately unbounded by default and not configurable yet: the
`(group_id, sent_at)` index and the `ondelete="CASCADE"` on `group_id` are
enough for a future purge job (`DELETE ... WHERE sent_at < cutoff`) to be
added later without a schema change.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from communeer.models.base import Base, uuid_pk


class MessageType(str, enum.Enum):
    text = "text"
    media = "media"
    # Reserved for a future `onmessage` payload shape Communeer doesn't yet
    # distinguish (e.g. group-system notices) — not populated today.
    system = "system"


class GroupMessage(Base):
    __tablename__ = "group_messages"
    __table_args__ = (
        UniqueConstraint("group_id", "wa_message_id", name="uq_group_message_wa_id"),
        Index("ix_group_messages_group_sent_at", "group_id", "sent_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable + SET NULL, not CASCADE — same posture as `AuditEvent.actor_user_id`:
    # `Member` rows are never hard-deleted anywhere in this codebase, so this
    # is defensive-but-currently-inert, not a real deletion path.
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    wa_message_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    message_type: Mapped[MessageType] = mapped_column(
        Enum(MessageType, native_enum=False, length=16), nullable=False, default=MessageType.text
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    group: Mapped["Group"] = relationship(back_populates="messages")  # noqa: F821
