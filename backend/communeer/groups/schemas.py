import uuid
from datetime import datetime

from communeer.models import ActivityType, MembershipStatus
from communeer.schemas import CamelModel


class GroupSummaryOut(CamelModel):
    id: uuid.UUID
    wa_id: str
    name: str
    description: str | None
    picture_url: str | None
    is_announcement_group: bool
    member_count: int
    member_limit: int | None
    pending_request_count: int
    admin_count: int
    last_message_at: datetime | None


class GroupDetailOut(GroupSummaryOut):
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
    last_message_at: datetime | None
    last_seen_at: datetime | None
    last_activity_type: ActivityType | None
    last_activity_at: datetime | None
    last_activity_content: str | None


class GroupRequestOut(CamelModel):
    member_id: uuid.UUID
    wa_id: str
    display_name: str
    requested_at: datetime | None


class GroupInviteLinkOut(CamelModel):
    # `None` is a real, honest answer (the connected account can't generate
    # one for this group right now — see `WhatsAppProvider.get_group_invite_link`),
    # not an error.
    invite_link: str | None
