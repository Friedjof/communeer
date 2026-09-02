"""Claim flow: how an auto-provisioned `group_admin` account (see
`auth/provisioning.py`) becomes actually usable.

Identification is phone number + 6-digit code — deliberately the exact same
shape as the login-OTP UX, not a separate opaque link-token — so this reuses
the entire existing WhatsApp-OTP challenge machinery verbatim: code
generation/hashing, the 5-minute expiry, the 30-second resend cooldown, and
(critically for brute-force protection on an *unauthenticated* endpoint) the
existing `failed_login_count`/`locked_until` lockout pair, which is
otherwise idle on an unclaimed account since no login attempt is reachable
yet.

No new session/2FA-setup UI is needed here: `complete_claim` sets a password
and issues a normal session (exactly like a password-only login), and from
then on the already-existing mandatory-2FA gate (`deps.get_current_user`)
and `/setup/2fa` redirect take over precisely as they do for a fresh
owner/admin account.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.auth.phone import normalize_phone_to_wa_id
from communeer.auth.provisioning import send_claim_code
from communeer.auth.security import hash_password, is_locked_out
from communeer.auth.service import (
    _record_failure,
    _record_success,
    _verify_pending_otp_code,
)
from communeer.config import Settings
from communeer.errors import ApiError, bad_request, conflict
from communeer.models import AuditEvent, Member, User
from communeer.providers.whatsapp.base import WhatsAppProvider


def _get_claimable_user_by_phone(db: Session, phone_number: str) -> User | None:
    """`None` for a claim that can't happen right now, for any reason — a
    genuinely unknown number, an already-claimed account, a deactivated one,
    or one an owner hasn't approved yet (`is_approved=False`, see
    `auth/provisioning.py`'s module docstring). All indistinguishable to the
    caller by design — see `request_claim`."""
    wa_id = normalize_phone_to_wa_id(phone_number)
    member = db.execute(select(Member).where(Member.wa_id == wa_id)).scalar_one_or_none()
    if member is None:
        return None
    user = db.execute(select(User).where(User.member_id == member.id)).scalar_one_or_none()
    if user is None or user.is_claimed or not user.is_active or not user.is_approved:
        return None
    return user


def request_claim(db: Session, provider: WhatsAppProvider, phone_number: str) -> None:
    """Always looks like a no-op success to the caller — no account-
    enumeration oracle. An unknown number, an already-claimed account, a
    deactivated account, an unapproved account, and a currently-locked-out
    account are all indistinguishable from the outside (silently does
    nothing in every case)."""
    user = _get_claimable_user_by_phone(db, phone_number)
    if user is None:
        return
    if is_locked_out(user.locked_until, now=datetime.now(UTC)):
        return
    try:
        send_claim_code(db, provider, user)
    except ApiError:
        # `_send_pending_otp` (via `send_claim_code`) already turns a
        # provider-connectivity failure — or a too-soon resend — into an
        # `ApiError`; swallow it here too, same no-oracle, no-hard-failure
        # reasoning as above. An owner can resend later.
        pass


def complete_claim(
    db: Session,
    settings: Settings,
    *,
    phone_number: str,
    code: str,
    username: str | None,
    password: str,
) -> User:
    user = _get_claimable_user_by_phone(db, phone_number)
    if user is None:
        raise bad_request("Invalid or expired code.")

    # Deliberately the same generic error as "no such claimable user" and
    # "wrong code" below — unlike the login flow's lockout check, this must
    # not leak via a distinguishable status code (429 vs 400) that a phone
    # number belongs to a real, approved, unclaimed account. See
    # `request_claim`'s no-oracle reasoning above.
    if is_locked_out(user.locked_until, now=datetime.now(UTC)):
        raise bad_request("Invalid or expired code.")

    if not _verify_pending_otp_code(db, user, code):
        _record_failure(db, user, settings)
        raise bad_request("Invalid or expired code.")

    final_username = username or user.username
    if final_username != user.username:
        clash = db.execute(
            select(User.id).where(User.username == final_username, User.id != user.id)
        ).scalar_one_or_none()
        if clash is not None:
            raise conflict(f"Username {final_username!r} is already taken.")
        user.username = final_username

    user.password_hash = hash_password(password)
    user.is_claimed = True
    user.claimed_at = datetime.now(UTC)
    user.token_version += 1
    _record_success(db, user)  # also resets failed_login_count/locked_until and commits

    db.add(
        AuditEvent(
            actor_user_id=user.id,
            action="auth.claimed",
            target_type="user",
            target_id=str(user.id),
            detail={"username": final_username},
        )
    )
    db.commit()
    db.refresh(user)
    return user
