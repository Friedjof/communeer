"""Owner-only CRUD over dashboard `User` accounts.

Distinct from `auth/service.py` (login/logout/session, actor-is-target audit
events): this module manages *other* users' accounts. Every mutation follows
the same inline `AuditEvent` + `db.commit()` pattern as `sync/service.py` and
`moderation/service.py` — `detail` never contains a plaintext password or
password hash.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from communeer.auth.security import hash_password
from communeer.errors import conflict, not_found
from communeer.models import AuditEvent, User, UserRole


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
