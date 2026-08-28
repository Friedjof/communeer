import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from communeer.models.base import Base, uuid_pk


class Community(Base):
    __tablename__ = "communities"

    id: Mapped[uuid.UUID] = uuid_pk()
    wa_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    picture_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    announcement_group_wa_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    groups: Mapped[list["Group"]] = relationship(  # noqa: F821
        back_populates="community", cascade="all, delete-orphan"
    )
