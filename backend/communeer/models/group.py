import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from communeer.models.base import Base, uuid_pk


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    community_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    wa_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    picture_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_announcement_group: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    member_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    community: Mapped["Community"] = relationship(back_populates="groups")  # noqa: F821
    memberships: Mapped[list["GroupMembership"]] = relationship(  # noqa: F821
        back_populates="group", cascade="all, delete-orphan"
    )
