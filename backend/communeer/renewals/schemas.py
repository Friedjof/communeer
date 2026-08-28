import uuid
from datetime import datetime

from communeer.models.renewal import RenewalConfirmationStatus
from communeer.renewals.service import DEFAULT_DEADLINE_DAYS
from communeer.schemas import CamelModel


class RenewalSuggestionOut(CamelModel):
    member_id: uuid.UUID
    wa_id: str
    display_name: str
    avatar_url: str | None
    phone_number_masked: str | None
    group_count: int
    joined_at: datetime | None
    # Always `True`: no message/read-receipt activity data exists in this
    # codebase yet, so every row is marked explicitly rather than silently
    # omitting an "activity" field the frontend might otherwise assume is
    # just empty for this member.
    activity_unknown: bool = True


class CreateRenewalCampaignIn(CamelModel):
    member_ids: list[uuid.UUID]
    deadline_days: int = DEFAULT_DEADLINE_DAYS


class RenewalCampaignSummaryOut(CamelModel):
    id: uuid.UUID
    community_id: uuid.UUID
    started_at: datetime
    deadline: datetime
    pending_count: int
    confirmed_count: int
    expired_count: int
    total_count: int


class RenewalConfirmationOut(CamelModel):
    member_id: uuid.UUID
    wa_id: str
    display_name: str
    status: RenewalConfirmationStatus
    is_expired: bool
    responded_at: datetime | None


class RenewalCampaignDetailOut(RenewalCampaignSummaryOut):
    confirmations: list[RenewalConfirmationOut]
