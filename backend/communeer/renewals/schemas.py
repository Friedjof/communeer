import uuid
from datetime import datetime

from pydantic import Field

from communeer.models import ActivityType
from communeer.models.renewal import RenewalConfirmationStatus
from communeer.renewals.service import DEFAULT_DEADLINE_DAYS
from communeer.schemas import CamelModel

# 1 day minimum (a 0-or-negative deadline would create an instantly-"expired"
# campaign with every confirmation silently doomed, no error); 365 days
# maximum (an absurdly large value would overflow the `now + timedelta(...)`
# arithmetic in `renewals/service.py`'s `create_renewal_campaign`, raising an
# unhandled `OverflowError` instead of a clean 422) — a year is already a
# generous outer bound for a membership-renewal campaign's deadline.
_MIN_DEADLINE_DAYS = 1
_MAX_DEADLINE_DAYS = 365


class RenewalSuggestionOut(CamelModel):
    member_id: uuid.UUID
    wa_id: str
    display_name: str
    avatar_url: str | None
    phone_number_masked: str | None
    joined_at: datetime | None
    # Real activity signals, straight off this member's `GroupMembership` row
    # for the one group a renewal round is scoped to (same fields
    # `MemberSummaryOut` exposes, just not aggregated across groups anymore).
    # `last_message_at` is a real, provider-observed signal for WPPConnect.
    # `last_seen_at` is almost always `None` in practice — WhatsApp doesn't
    # expose presence data for most accounts (verified live against real
    # group members) — the frontend renders that as "not available", not
    # "unknown".
    last_message_at: datetime | None
    last_seen_at: datetime | None
    last_activity_type: ActivityType | None
    last_activity_at: datetime | None
    last_activity_content: str | None


class CreateRenewalCampaignIn(CamelModel):
    member_ids: list[uuid.UUID]
    deadline_days: int = Field(default=DEFAULT_DEADLINE_DAYS, ge=_MIN_DEADLINE_DAYS, le=_MAX_DEADLINE_DAYS)


class RenewalCampaignSummaryOut(CamelModel):
    id: uuid.UUID
    group_id: uuid.UUID
    started_at: datetime
    deadline: datetime
    pending_count: int
    confirmed_count: int
    expired_count: int
    total_count: int
    archived_at: datetime | None


class RenewalConfirmationOut(CamelModel):
    member_id: uuid.UUID
    wa_id: str
    display_name: str
    status: RenewalConfirmationStatus
    is_expired: bool
    responded_at: datetime | None
    reminder_sent_at: datetime | None
    declined_at: datetime | None
    removed_at: datetime | None


class RenewalCampaignDetailOut(RenewalCampaignSummaryOut):
    confirmations: list[RenewalConfirmationOut]
