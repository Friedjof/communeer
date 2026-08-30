import uuid
from datetime import datetime

from communeer.models import ActivityType
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
    # Real activity signals, aggregated (max) across this member's groups in
    # this community. `last_seen_at` is almost always `None` in practice —
    # WhatsApp doesn't expose presence data for most accounts (verified
    # live) — the frontend renders that as "not available", not "unknown".
    last_message_at: datetime | None
    last_seen_at: datetime | None
    # Unified "last activity" (message/reaction/view), aggregated the same
    # way as last_message_at/last_seen_at above: whichever of this member's
    # group memberships in this community has the most recent
    # last_activity_at wins, and its type+content come along with it.
    last_activity_type: ActivityType | None
    last_activity_at: datetime | None
    last_activity_content: str | None


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
