"""Idempotent seeding of the single admin user, run on app startup."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from communeer.auth.security import hash_password
from communeer.config import get_settings
from communeer.models import User, UserRole


def seed_admin_user(db: Session) -> None:
    settings = get_settings()
    user_count = db.execute(select(func.count()).select_from(User)).scalar_one()
    if user_count > 0:
        return

    admin = User(
        username=settings.seed_admin_username,
        password_hash=hash_password(settings.seed_admin_password),
        role=UserRole.owner,
        is_active=True,
    )
    db.add(admin)
    db.commit()
