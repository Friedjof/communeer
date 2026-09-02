"""Login flow: password step, optional second-factor step(s), and the shared
brute-force lockout counter between them.

Two-step login when `user.totp_enabled or user.whatsapp_otp_enabled`:
`authenticate_password()` succeeds but the caller (`auth/router.py`) issues a
short-lived pending-2FA cookie instead of a full session, and either
`verify_totp_step()` or `verify_whatsapp_otp_login_step()` completes it,
depending on which factor(s) the account has and which the user picks. All
verify steps share one `failed_login_count`/`locked_until` pair on `User` so
an attacker can't dodge the lockout by switching which factor they're
guessing.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from communeer.auth.security import (
    PENDING_2FA_MAX_AGE_SECONDS,
    WHATSAPP_OTP_RESEND_COOLDOWN_SECONDS,
    build_whatsapp_otp_message,
    decrypt_totp_secret,
    generate_otp_code,
    generate_recovery_codes,
    hash_password,
    is_locked_out,
    verify_password,
    verify_totp_code,
)
from communeer.config import Settings
from communeer.errors import (
    bad_request,
    conflict,
    service_unavailable,
    too_many_requests,
)
from communeer.models import AuditEvent, User, UserRecoveryCode
from communeer.providers.whatsapp.base import (
    WhatsAppNotConnectedError,
    WhatsAppProvider,
    WhatsAppProviderUnavailableError,
)


@dataclass
class PasswordStepResult:
    user: User
    requires_2fa: bool


def _check_not_locked_out(user: User) -> None:
    if is_locked_out(user.locked_until, now=datetime.now(UTC)):
        raise too_many_requests("Too many failed attempts. Please try again later.")


def _record_failure(db: Session, user: User, settings: Settings) -> None:
    user.failed_login_count += 1
    if user.failed_login_count >= settings.login_max_failed_attempts:
        user.locked_until = datetime.now(UTC) + timedelta(seconds=settings.login_lockout_seconds)
        user.failed_login_count = 0
    db.commit()


def _record_success(db: Session, user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()


def authenticate_password(db: Session, username: str, password: str, settings: Settings) -> PasswordStepResult | None:
    """The password step of login. Returns `None` for any of "no such user",
    "inactive", "unclaimed", or "wrong password" — deliberately
    indistinguishable to the caller, same as before 2FA existed. Raises
    `too_many_requests` if the account is currently locked out (checked
    *before* verifying the password, so a locked-out account never leaks
    whether the password itself is even correct).

    `not user.is_claimed` is defense in depth for an auto-provisioned
    `group_admin` account (see `auth/provisioning.py`): its password is
    already an unguessable random value nobody was ever given, so this
    branch should be unreachable in practice, but makes the invariant
    "an unclaimed account can never produce a session" explicit and
    machine-checked rather than merely true by construction."""
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None or not user.is_active or not user.is_claimed:
        return None

    _check_not_locked_out(user)

    if not verify_password(password, user.password_hash):
        _record_failure(db, user, settings)
        return None

    requires_2fa = user.totp_enabled or user.whatsapp_otp_enabled
    if not requires_2fa:
        _record_success(db, user)

    return PasswordStepResult(user=user, requires_2fa=requires_2fa)


def verify_totp_step(db: Session, user: User, code: str, settings: Settings) -> bool:
    """The second step for a `totp_enabled` user: `code` may be either a
    live TOTP code or an unused recovery code (consumed on success). Shares
    the same lockout counter as the password step."""
    _check_not_locked_out(user)

    if _verify_live_totp(user, code) or _consume_recovery_code(db, user, code):
        _record_success(db, user)
        return True

    _record_failure(db, user, settings)
    return False


def _verify_live_totp(user: User, code: str) -> bool:
    if not user.totp_secret_encrypted:
        return False
    secret = decrypt_totp_secret(user.totp_secret_encrypted)
    return secret is not None and verify_totp_code(secret, code)


def _consume_recovery_code(db: Session, user: User, code: str) -> bool:
    unused = db.execute(
        select(UserRecoveryCode).where(UserRecoveryCode.user_id == user.id, UserRecoveryCode.used_at.is_(None))
    ).scalars()
    for recovery_code in unused:
        if verify_password(code, recovery_code.code_hash):
            recovery_code.used_at = datetime.now(UTC)
            db.commit()
            return True
    return False


# ---------------------------------------------------------------------------
# Recovery codes — generic backup for "any 2FA factor," not TOTP-specific.
# ---------------------------------------------------------------------------


def replace_recovery_codes(db: Session, user: User) -> list[str]:
    """Wholesale-replaces (never appends to) this user's recovery codes."""
    db.execute(delete(UserRecoveryCode).where(UserRecoveryCode.user_id == user.id))
    codes = generate_recovery_codes()
    for code in codes:
        db.add(UserRecoveryCode(user_id=user.id, code_hash=hash_password(code)))
    return codes


def has_any_recovery_codes(db: Session, user: User) -> bool:
    return (
        db.execute(select(UserRecoveryCode.id).where(UserRecoveryCode.user_id == user.id).limit(1)).scalar_one_or_none()
        is not None
    )


def clear_recovery_codes_if_no_factor_remains(db: Session, user: User) -> None:
    """Recovery codes are only meaningful as a backup for an active 2FA
    factor — called after a caller has already flipped its own factor off,
    this wipes them only if *neither* factor is enabled anymore. Disabling
    one of two active factors deliberately leaves the codes intact."""
    if not user.totp_enabled and not user.whatsapp_otp_enabled:
        db.execute(delete(UserRecoveryCode).where(UserRecoveryCode.user_id == user.id))


# ---------------------------------------------------------------------------
# WhatsApp-OTP — a second, independent 2FA factor. Structurally mirrors the
# TOTP functions above (a login step sharing the lockout counter, a
# setup/enable/disable self-service trio) except the "secret" is a fresh,
# short-lived code delivered via WhatsApp DM instead of a persistent pyotp
# secret — see `models/user.py`'s `pending_otp_*` columns.
# ---------------------------------------------------------------------------


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _verify_pending_otp_code(db: Session, user: User, code: str) -> bool:
    """Checks `code` against the one in-flight OTP challenge on `user` (used
    for both setup- and login-time verification — see `models/user.py`'s
    column docstring for why one shared slot is safe). Expires after
    `PENDING_2FA_MAX_AGE_SECONDS`. Consumes the challenge (clears both
    pending fields) on success so it can't be replayed; no lockout side
    effects here — the caller decides whether this attempt counts (see
    `verify_whatsapp_otp_login_step` vs. `enable_whatsapp_otp`)."""
    sent_at = _as_utc(user.pending_otp_sent_at)
    if not user.pending_otp_code_hash or sent_at is None:
        return False
    if datetime.now(UTC) - sent_at > timedelta(seconds=PENDING_2FA_MAX_AGE_SECONDS):
        return False
    if not verify_password(code, user.pending_otp_code_hash):
        return False

    user.pending_otp_code_hash = None
    user.pending_otp_sent_at = None
    db.commit()
    return True


def verify_whatsapp_otp_login_step(db: Session, user: User, code: str, settings: Settings) -> bool:
    """The second step for a `whatsapp_otp_enabled` user: `code` may be
    either the just-sent WhatsApp code or an unused recovery code (same
    symmetry as `verify_totp_step`). Shares the same lockout counter as the
    password step and the TOTP verify step."""
    _check_not_locked_out(user)

    if _verify_pending_otp_code(db, user, code) or _consume_recovery_code(db, user, code):
        _record_success(db, user)
        return True

    _record_failure(db, user, settings)
    return False


def _send_pending_otp(db: Session, provider: WhatsAppProvider, user: User, target_wa_id: str) -> None:
    """Shared send primitive for both setup- and login-time OTP requests:
    enforces the resend cooldown, generates+stores a fresh hashed code, and
    sends it. Any staged-but-uncommitted change a caller made before calling
    this (e.g. `request_whatsapp_otp_setup` staging `pending_phone_wa_id`) is
    only persisted together with the OTP fields below, in the one commit at
    the end — so a failed send never leaves a half-updated row."""
    sent_at = _as_utc(user.pending_otp_sent_at)
    if sent_at is not None and datetime.now(UTC) - sent_at < timedelta(seconds=WHATSAPP_OTP_RESEND_COOLDOWN_SECONDS):
        raise too_many_requests("Please wait a moment before requesting another code.")

    code = generate_otp_code()
    try:
        provider.send_text_message(target_wa_id, build_whatsapp_otp_message(code))
    except (WhatsAppNotConnectedError, WhatsAppProviderUnavailableError) as exc:
        raise service_unavailable(
            "Could not send a WhatsApp message right now. Please try again shortly, or use another sign-in method."
        ) from exc

    user.pending_otp_code_hash = hash_password(code)
    user.pending_otp_sent_at = datetime.now(UTC)
    db.commit()


def request_whatsapp_otp_setup(db: Session, provider: WhatsAppProvider, user: User, phone_wa_id: str) -> None:
    if user.whatsapp_otp_enabled:
        raise conflict("WhatsApp login codes are already enabled. Disable them first to set up a new number.")

    user.pending_phone_wa_id = phone_wa_id
    _send_pending_otp(db, provider, user, phone_wa_id)


def request_whatsapp_otp_login(db: Session, provider: WhatsAppProvider, user: User) -> None:
    _check_not_locked_out(user)
    if not user.whatsapp_otp_enabled or not user.phone_wa_id:
        raise bad_request("WhatsApp login codes are not enabled for this account.")

    _send_pending_otp(db, provider, user, user.phone_wa_id)


def enable_whatsapp_otp(db: Session, user: User, code: str) -> list[str] | None:
    if user.whatsapp_otp_enabled:
        raise conflict("WhatsApp login codes are already enabled.")
    if not user.pending_phone_wa_id:
        raise bad_request("Call /auth/2fa/whatsapp/setup first.")
    if not _verify_pending_otp_code(db, user, code):
        raise bad_request("Invalid or expired code. Please try again.")

    user.phone_wa_id = user.pending_phone_wa_id
    user.pending_phone_wa_id = None
    user.whatsapp_otp_enabled = True
    user.token_version += 1  # invalidate any other sessions for this account

    # Deliberate deviation from `enable_totp`, which always replaces the
    # recovery-code set: adding a *second* factor shouldn't invalidate codes
    # the user already saved from enabling their first one.
    codes = None if has_any_recovery_codes(db, user) else replace_recovery_codes(db, user)

    db.commit()
    return codes


def disable_whatsapp_otp(db: Session, user: User) -> None:
    user.whatsapp_otp_enabled = False
    user.phone_wa_id = None
    user.pending_phone_wa_id = None
    user.pending_otp_code_hash = None
    user.pending_otp_sent_at = None
    user.token_version += 1

    clear_recovery_codes_if_no_factor_remains(db, user)
    db.commit()


def record_auth_event(db: Session, *, action: str, actor_user_id: uuid.UUID | None = None, detail: dict | None = None) -> None:
    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action=action,
            target_type="user",
            target_id=str(actor_user_id) if actor_user_id else None,
            detail=detail,
        )
    )
    db.commit()
