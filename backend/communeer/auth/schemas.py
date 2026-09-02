import uuid

from pydantic import BaseModel, Field

from communeer.models import UserRole
from communeer.schemas import CamelModel


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=255)


class UserOut(CamelModel):
    id: uuid.UUID
    username: str
    role: UserRole
    totp_enabled: bool
    whatsapp_otp_enabled: bool


class LoginTotpRequiredOut(CamelModel):
    requires_totp: bool = True
    # Which factor(s) this account has enabled — lets the frontend decide
    # whether to go straight to the TOTP stage (today's behavior, when only
    # `totp_enabled` is true), straight to the WhatsApp stage, or offer a
    # choice when both are true.
    totp_enabled: bool
    whatsapp_otp_enabled: bool


class VerifyTotpIn(BaseModel):
    code: str = Field(max_length=32)


class TotpSetupOut(CamelModel):
    secret: str
    otpauth_uri: str


class TotpEnableIn(BaseModel):
    code: str = Field(max_length=32)


class RecoveryCodesOut(CamelModel):
    recovery_codes: list[str]


class PasswordConfirmIn(BaseModel):
    password: str = Field(max_length=255)


class WhatsAppOtpSetupIn(CamelModel):
    phone_number: str = Field(max_length=32)


class WhatsAppOtpSetupOut(CamelModel):
    phone_wa_id: str


class VerifyWhatsappOtpIn(BaseModel):
    code: str = Field(max_length=32)


class WhatsAppOtpEnableOut(CamelModel):
    # `None` when the user already had a valid set of recovery codes from an
    # earlier-enabled factor — adding a second factor never invalidates
    # codes the user already saved (see `auth/service.py::enable_whatsapp_otp`).
    recovery_codes: list[str] | None


class ClaimRequestIn(CamelModel):
    phone_number: str = Field(max_length=32)


class ClaimCompleteIn(CamelModel):
    phone_number: str = Field(max_length=32)
    code: str = Field(max_length=32)
    username: str | None = Field(default=None, min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=255)
