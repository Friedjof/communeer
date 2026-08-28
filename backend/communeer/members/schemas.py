import uuid
from datetime import datetime

from communeer.models import MembershipStatus
from communeer.schemas import CamelModel


class MemberMembershipOut(CamelModel):
    group_id: uuid.UUID
    group_name: str
    community_id: uuid.UUID
    community_name: str
    is_admin: bool
    status: MembershipStatus
    joined_at: datetime | None


class MemberDetailOut(CamelModel):
    id: uuid.UUID
    wa_id: str
    display_name: str
    phone_number_masked: str | None
    avatar_url: str | None
    is_business: bool
    first_seen_at: datetime
    memberships: list[MemberMembershipOut]
