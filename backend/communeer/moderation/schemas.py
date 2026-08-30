import uuid
from datetime import datetime
from typing import Literal

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


class ModerationQueueOut(CamelModel):
    admin_coverage_gaps: list[AdminCoverageGapOut]
    never_active_members: list[NeverActiveMemberOut]
    join_bursts: list[JoinBurstOut]
    capacity_attention: list[CapacityAttentionOut]


class DismissModerationItemIn(CamelModel):
    section: Literal["admin_coverage_gaps", "never_active_members", "join_bursts", "capacity_attention"]
    target_id: str
    reason: str | None = None
