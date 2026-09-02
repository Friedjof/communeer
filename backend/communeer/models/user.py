import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from communeer.models.base import Base, uuid_pk


class UserRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    # Scoped to only the WhatsApp group(s) this account's linked `Member` is
    # `GroupMembership.is_admin=True` for (see `authz.py`) — never assignable
    # by hand (`users/service.py` rejects it), only auto-provisioned by
    # `auth/provisioning.py` when a real WhatsApp group admin is synced.
    group_admin = "group_admin"
    viewer = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=16), nullable=False, default=UserRole.admin
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # -- TOTP two-factor auth --------------------------------------------
    # Fernet-encrypted (never plaintext) — unlike `password_hash`, this must
    # be *readable* server-side to verify a code, so it can't be a one-way
    # hash. `totp_enabled` only flips to `True` once the user has confirmed
    # a real code from their authenticator app works (see `auth/router.py`'s
    # `/auth/2fa/enable`) — never "enabled" on an unconfirmed secret.
    totp_secret_encrypted: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # -- WhatsApp-message two-factor auth ---------------------------------
    # A second, independent 2FA factor alongside TOTP above — a user may have
    # either, both, or (transiently, mid-setup) neither. `phone_wa_id` is the
    # user's OWN verified WhatsApp number (normalized "<digits>@c.us", see
    # `auth/phone.py`), never the connected WhatsApp account's own number —
    # there's no reliable way to learn that programmatically (see
    # `providers/whatsapp/wppconnect.py`'s `get_own_wa_id` docstring), and it
    # wouldn't distinguish between multiple dashboard users anyway.
    # `whatsapp_otp_enabled` only flips to `True` once `/auth/2fa/whatsapp/enable`
    # confirms a real code sent to the number works — same "never enabled on
    # an unconfirmed secret" discipline as `totp_enabled`.
    phone_wa_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    whatsapp_otp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The not-yet-confirmed number entered during setup — kept separate from
    # `phone_wa_id` so an in-progress setup attempt never clobbers an
    # already-working verified number until the code is actually confirmed.
    pending_phone_wa_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # One shared "in-flight OTP challenge" slot, reused for both the
    # setup-time phone-verification code and the login-time code — the two
    # can never coexist for one user (a setup challenge only exists while
    # `whatsapp_otp_enabled` is `False`; a login challenge only while it's
    # `True`), so no separate `purpose` discriminator is needed. Hashed via
    # the same `hash_password`/`verify_password` Argon2 helpers as recovery
    # codes below.
    pending_otp_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pending_otp_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Bumped on password change, role change, and 2FA enable/disable so any
    # session token signed before the bump is rejected by `get_current_user`
    # even though its signature is still technically valid — closes the
    # "stolen cookie survives a password reset" gap a stateless signed
    # cookie would otherwise have.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # -- Login brute-force protection ------------------------------------
    # Shared between the password step and the TOTP-verification step (see
    # `auth/service.py`) so an attacker can't reset the counter by switching
    # which factor they're guessing.
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # -- Link to a WhatsApp identity, for auto-provisioned `group_admin`
    # accounts (see `auth/provisioning.py`) ------------------------------
    # `SET NULL`, not `CASCADE`: a `Member` is never hard-deleted anywhere in
    # this codebase today, so this is defensive-but-currently-inert (same
    # posture as `GroupMessage.member_id`) — if it ever did happen, the
    # account should degrade to "administers nothing" (see `authz.py`), not
    # vanish. `unique=True`: one dashboard account per WhatsApp identity;
    # a plain SQL UNIQUE column allows unlimited `NULL`s (owner/admin/viewer
    # never set this), so it costs those rows nothing.
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL"), nullable=True, unique=True, index=True
    )
    # Whether the real person behind an auto-provisioned account has
    # confirmed control of it yet (see `auth/claim_service.py`). Defaults to
    # `True` so every pre-existing/manually-created account (owner/admin/
    # viewer) is unaffected — provisioning explicitly sets this `False`.
    # `authenticate_password` rejects login while this is `False`, as
    # defense in depth on top of the unguessable placeholder password an
    # unclaimed account is created with.
    is_claimed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Whether an owner/admin has explicitly released an auto-provisioned
    # account to receive its claim code — nothing about discovering or
    # syncing a WhatsApp group admin ever sends a message on its own
    # (see `auth/provisioning.py`); a message only ever goes out as the
    # direct result of an owner clicking "Approve" (`users/service.py::
    # approve_group_admin`), which sets this `True` and sends in the same
    # action. Defaults to `True` for the same reason `is_claimed` does:
    # every pre-existing/manually-created account (owner/admin/viewer) is
    # unaffected — provisioning explicitly sets this `False`.
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    recovery_codes: Mapped[list["UserRecoveryCode"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserRecoveryCode(Base):
    """One single-use TOTP recovery code, hashed at rest exactly like a
    password (via `auth.security.hash_password`/`verify_password`) — never
    stored in plaintext. A full set (10) is generated when 2FA is enabled
    and wholesale replaced (not appended to) on regeneration."""

    __tablename__ = "user_recovery_codes"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    user: Mapped["User"] = relationship(back_populates="recovery_codes")
