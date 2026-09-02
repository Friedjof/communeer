import uuid
from datetime import datetime

from pydantic import Field

from communeer.models import UserRole
from communeer.schemas import CamelModel


class ManagedUserOut(CamelModel):
    id: uuid.UUID
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    totp_enabled: bool
    # Set only for auto-provisioned `group_admin` accounts (see
    # `auth/provisioning.py`) — `None`/`True`/`True`/`None` respectively for
    # every owner/admin/viewer account, which are never linked to a WhatsApp
    # identity and are always "claimed"/"approved" by construction.
    member_id: uuid.UUID | None
    is_claimed: bool
    # Whether an owner has released this account to receive its claim code
    # yet — `False` for a newly-discovered, not-yet-reviewed group admin.
    # See `auth/provisioning.py`'s module docstring.
    is_approved: bool
    claimed_at: datetime | None
    # `None` for every owner/admin/viewer account (never linked to a WhatsApp
    # identity) — set for a `group_admin` account so a send-confirmation
    # dialog (see `UsersPage.tsx`) can show who a claim-code message actually
    # goes to.
    phone_number_masked: str | None


class CreateUserIn(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)
    role: UserRole


class UpdateUserIn(CamelModel):
    role: UserRole | None = None
    is_active: bool | None = None


class ResetPasswordIn(CamelModel):
    password: str = Field(min_length=8)
