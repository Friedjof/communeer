import uuid
from datetime import datetime

from communeer.models import MembershipStatus
from communeer.schemas import CamelModel


class GroupSummaryOut(CamelModel):
    id: uuid.UUID
    wa_id: str
    name: str
    picture_url: str | None
    is_announcement_group: bool
    member_count: int
    member_limit: int | None
    pending_request_count: int


class GroupDetailOut(GroupSummaryOut):
    description: str | None
    community_id: uuid.UUID
    community_name: str


class GroupDetailAdvancedOut(GroupDetailOut):
    raw_metadata: dict | None


class GroupMemberOut(CamelModel):
    member_id: uuid.UUID
    wa_id: str
    display_name: str
    avatar_url: str | None
    is_admin: bool
    is_super_admin: bool
    status: MembershipStatus
    joined_at: datetime | None


class GroupRequestOut(CamelModel):
    member_id: uuid.UUID
    wa_id: str
    display_name: str
    requested_at: datetime | None
