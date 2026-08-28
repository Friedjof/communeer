from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.auth.security import verify_password
from communeer.models import AuditEvent, User


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def record_auth_event(db: Session, *, action: str, actor_user_id=None, detail: dict | None = None) -> None:
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
