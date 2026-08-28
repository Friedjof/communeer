"""Growth-history snapshots.

`Community.member_count`/`group_count` and `Group.member_count`/
`pending_request_count` are point-in-time values, overwritten on every sync —
there is no way to reconstruct a "how did this grow over time" chart from
them alone. These two tables exist purely to hold that time series: one row
per community (and one row per group) written at the end of every
`sync_community()` call, never updated or deduplicated afterwards — repeated
syncs are expected to produce repeated rows with different `recorded_at`
values, since that repetition *is* the time series.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from communeer.models.base import Base, uuid_pk


class CommunityMemberSnapshot(Base):
    __tablename__ = "community_member_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    community_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    group_count: Mapped[int] = mapped_column(Integer, nullable=False)
    admin_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GroupMemberSnapshot(Base):
    __tablename__ = "group_member_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
