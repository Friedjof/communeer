"""Owner-only CRUD over dashboard `User` accounts.

Distinct from `auth/service.py` (login/logout/session, actor-is-target audit
events): this module manages *other* users' accounts. Every mutation follows
the same inline `AuditEvent` + `db.commit()` pattern as `sync/service.py` and
`moderation/service.py` — `detail` never contains a plaintext password or
password hash.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from communeer.auth.provisioning import send_claim_code
from communeer.auth.security import hash_password
from communeer.errors import bad_request, conflict, not_found, service_unavailable
from communeer.models import AuditEvent, User, UserRecoveryCode, UserRole
from communeer.providers.whatsapp.base import (
    WhatsAppNotConnectedError,
    WhatsAppProvider,
    WhatsAppProviderUnavailableError,
)


def _get_owner_count(db: Session) -> int:
    return len(list(db.execute(select(User).where(User.role == UserRole.owner, User.is_active.is_(True))).scalars()))


def _get_user_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User not found.")
    return user


def list_users(db: Session) -> list[User]:
    return list(db.execute(select(User).order_by(User.created_at)).scalars())


def create_user(db: Session, *, username: str, password: str, role: UserRole, actor_user_id: uuid.UUID) -> User:
    if role is UserRole.group_admin:
        raise bad_request("group_admin accounts are created automatically when a WhatsApp group admin is synced.")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict(f"Username {username!r} is already taken.") from exc

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="user.created",
            target_type="user",
            target_id=str(user.id),
            detail={"username": username, "role": role.value},
        )
    )
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user_id: uuid.UUID,
    *,
    role: UserRole | None,
    is_active: bool | None,
    actor_user_id: uuid.UUID,
) -> User:
    user = _get_user_or_404(db, user_id)

    # Assignment *to* group_admin is only ever automatic (see `create_user`).
    # Moving *away* from it (e.g. promoting a claimed group_admin to full
    # `admin`) is still allowed — only this one direction is blocked.
    if role is UserRole.group_admin:
        raise bad_request("group_admin accounts are created automatically when a WhatsApp group admin is synced.")

    # Guard against a self-inflicted or last-owner lockout: neither the acting
    # user themselves nor the last remaining active owner can be deactivated,
    # and the last remaining active owner can't be demoted away from `owner`
    # either — either would leave the workspace with no one able to manage it.
    would_deactivate = is_active is False and user.is_active
    would_demote_owner = role is not None and role != UserRole.owner and user.role == UserRole.owner

    if user_id == actor_user_id and would_deactivate:
        raise conflict("You cannot deactivate your own account.")

    is_last_active_owner = user.role == UserRole.owner and user.is_active and _get_owner_count(db) <= 1
    if is_last_active_owner and (would_deactivate or would_demote_owner):
        raise conflict("Cannot remove the only remaining owner.")

    changes: dict[str, object] = {}
    if role is not None and role != user.role:
        changes["role"] = {"from": user.role.value, "to": role.value}
        user.role = role
        user.token_version += 1  # a role change invalidates any existing session
    if is_active is not None and is_active != user.is_active:
        changes["isActive"] = {"from": user.is_active, "to": is_active}
        user.is_active = is_active

    if changes:
        db.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                action="user.updated",
                target_type="user",
                target_id=str(user.id),
                detail=changes,
            )
        )

    db.commit()
    db.refresh(user)
    return user


def reset_user_password(db: Session, user_id: uuid.UUID, *, new_password: str, actor_user_id: uuid.UUID) -> None:
    user = _get_user_or_404(db, user_id)
    user.password_hash = hash_password(new_password)
    user.token_version += 1  # invalidate any session signed with the old password

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="user.password_reset",
            target_type="user",
            target_id=str(user.id),
            detail=None,
        )
    )
    db.commit()


def reset_user_2fa(db: Session, user_id: uuid.UUID, *, actor_user_id: uuid.UUID) -> None:
    """Owner-only recovery path for a locked-out teammate: wipes *all* 2FA
    state (both TOTP and WhatsApp-OTP, not just one), since the point of a
    2FA reset is "they can't get in with what they have" — leaving a second
    factor dangling would be misleading (if it still worked, they wouldn't
    need this). They're routed back through the mandatory setup flow on
    their next login (see `deps.get_current_user`'s owner/admin requirement)."""
    user = _get_user_or_404(db, user_id)
    user.totp_enabled = False
    user.totp_secret_encrypted = None
    user.whatsapp_otp_enabled = False
    user.phone_wa_id = None
    user.pending_phone_wa_id = None
    user.pending_otp_code_hash = None
    user.pending_otp_sent_at = None
    user.token_version += 1
    db.execute(delete(UserRecoveryCode).where(UserRecoveryCode.user_id == user.id))

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="user.2fa_reset",
            target_type="user",
            target_id=str(user.id),
            detail=None,
        )
    )
    db.commit()


def approve_group_admin(
    db: Session, provider: WhatsAppProvider, user_id: uuid.UUID, *, actor_user_id: uuid.UUID
) -> None:
    """The one and only place a message goes out as a *result of* auto-
    provisioning (see `auth/provisioning.py`'s module docstring): discovering
    or syncing a real WhatsApp group admin never sends anything on its own,
    only ever creates an unclaimed, unapproved account — an owner must
    explicitly approve each one, right here, before they're ever contacted.

    Approval itself always takes effect, even if the send below fails —
    a provider hiccup shouldn't force the owner to redo the decision, just
    retry via `resend_claim_code`."""
    user = _get_user_or_404(db, user_id)
    if user.member_id is None or user.role is not UserRole.group_admin:
        raise bad_request("This account is not a pending group admin approval.")
    if user.is_claimed:
        raise bad_request("This account is already claimed.")
    if user.is_approved:
        raise conflict("This account is already approved.")

    user.is_approved = True
    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="user.group_admin_approved",
            target_type="user",
            target_id=str(user.id),
            detail=None,
        )
    )
    db.commit()

    try:
        send_claim_code(db, provider, user)
    except (WhatsAppNotConnectedError, WhatsAppProviderUnavailableError) as exc:
        raise service_unavailable(
            'Approved, but could not send the WhatsApp message right now. Use "Resend claim code" to try again.'
        ) from exc


def resend_claim_code(db: Session, provider: WhatsAppProvider, user_id: uuid.UUID, *, actor_user_id: uuid.UUID) -> None:
    """Owner-initiated resend for an approved-but-still-unclaimed
    `group_admin` account. Unlike `approve_group_admin` (which also flips
    `is_approved`), a failure here IS surfaced (503) — this is an explicit,
    interactive action an owner is waiting on, not the one-time approval
    decision."""
    user = _get_user_or_404(db, user_id)
    if user.member_id is None or user.is_claimed or not user.is_approved:
        raise bad_request("This account has no pending, approved claim to resend.")

    try:
        send_claim_code(db, provider, user)
    except (WhatsAppNotConnectedError, WhatsAppProviderUnavailableError) as exc:
        raise service_unavailable("Could not send a WhatsApp message right now. Please try again shortly.") from exc

    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="user.claim_code_resent",
            target_type="user",
            target_id=str(user.id),
            detail=None,
        )
    )
    db.commit()
