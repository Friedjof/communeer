from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from communeer.auth.security import read_session_token
from communeer.config import Settings, get_settings
from communeer.db import SessionLocal
from communeer.errors import unauthorized
from communeer.models import User
from communeer.providers.whatsapp import get_provider as _get_provider
from communeer.providers.whatsapp.base import WhatsAppProvider


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_provider() -> WhatsAppProvider:
    return _get_provider()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Load the current user from the signed session cookie.

    Always re-loads the `User` row from the DB (rather than trusting the
    cookie payload alone) so a deactivated user is rejected even while their
    session signature is still technically valid.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise unauthorized()

    user_id = read_session_token(token)
    if user_id is None:
        raise unauthorized()

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized()

    return user
