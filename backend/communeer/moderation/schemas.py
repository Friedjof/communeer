import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from communeer.groups.schemas import GroupRequestOut
from communeer.schemas import CamelModel


class AdminCoverageGapOut(CamelModel):
    group_id: uuid.UUID
    group_name: str
    admin_count: int


class NeverActiveMemberOut(CamelModel):
    member_id: uuid.UUID
    wa_id: str
    display_name: str
    avatar_url: str | None
    phone_number_masked: str | None
    group_count: int
    joined_at: datetime | None


class JoinBurstOut(CamelModel):
    group_id: uuid.UUID
    group_name: str
    member_count: int
    recent_join_count: int


class CapacityAttentionOut(CamelModel):
    group_id: uuid.UUID
    group_name: str
    member_count: int
    member_limit: int | None
    pending_request_count: int
    percent_full: float | None
    reason: Literal["capacity", "requests", "both"]
    # Populated only when `reason` is "requests"/"both" — lets the Moderation
    # page act on these inline instead of only linking into the group's
    # Requests tab. Reuses `GroupRequestOut` as-is (same shape the
    # per-group `GET /groups/{id}/requests` route already returns).
    pending_requests: list[GroupRequestOut] = Field(default_factory=list)


class MessageBurstOut(CamelModel):
    group_membership_id: uuid.UUID
    group_id: uuid.UUID
    group_name: str
    member_id: uuid.UUID
    member_display_name: str
    member_avatar_url: str | None
    message_count: int
    window_minutes: int


class DuplicateContentOut(CamelModel):
    group_membership_id: uuid.UUID
    group_id: uuid.UUID
    group_name: str
    member_id: uuid.UUID
    member_display_name: str
    content_preview: str
    occurrence_count: int


class ModerationQueueOut(CamelModel):
    admin_coverage_gaps: list[AdminCoverageGapOut]
    never_active_members: list[NeverActiveMemberOut]
    join_bursts: list[JoinBurstOut]
    capacity_attention: list[CapacityAttentionOut]
    message_bursts: list[MessageBurstOut]
    duplicate_content: list[DuplicateContentOut]


class DismissModerationItemIn(CamelModel):
    section: Literal[
        "admin_coverage_gaps",
        "never_active_members",
        "join_bursts",
        "capacity_attention",
        "message_bursts",
        "duplicate_content",
    ]
    target_id: str
    reason: str | None = None
