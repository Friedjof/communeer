import uuid
from datetime import datetime

from communeer.schemas import CamelModel


class CommunitySummaryOut(CamelModel):
    id: uuid.UUID
    wa_id: str
    name: str
    picture_url: str | None
    member_count: int
    group_count: int
    admin_count: int
    pending_request_count: int
    last_synced_at: datetime | None


class CommunityDetailOut(CommunitySummaryOut):
    description: str | None
    announcement_group_wa_id: str | None


class CommunityDetailAdvancedOut(CommunityDetailOut):
    raw_metadata: dict | None


class MemberSummaryOut(CamelModel):
    id: uuid.UUID
    wa_id: str
    display_name: str
    avatar_url: str | None
    phone_number_masked: str | None
    is_admin: bool
    is_community_admin: bool
    group_count: int
    joined_at: datetime | None


class CommunityHistoryPointOut(CamelModel):
    recorded_at: datetime
    member_count: int
    group_count: int
    admin_count: int
    pending_request_count: int


class GroupHistoryPointOut(CamelModel):
    recorded_at: datetime
    member_count: int
    pending_request_count: int


class GroupHistorySeriesOut(CamelModel):
    group_id: uuid.UUID
    group_name: str
    snapshots: list[GroupHistoryPointOut]
