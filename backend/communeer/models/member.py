import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from communeer.models.base import Base, uuid_pk


class Member(Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = uuid_pk()
    wa_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number_masked: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_business: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    memberships: Mapped[list["GroupMembership"]] = relationship(  # noqa: F821
        back_populates="member", cascade="all, delete-orphan"
    )
