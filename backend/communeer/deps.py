import uuid
from collections.abc import Callable, Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from communeer.auth.security import read_session_token
from communeer.authz import ensure_community_access, ensure_group_access
from communeer.config import Settings, get_settings
from communeer.db import SessionLocal
from communeer.errors import forbidden, totp_setup_required, unauthorized
from communeer.models import User, UserRole
from communeer.providers.whatsapp import get_provider as _get_provider
from communeer.providers.whatsapp.base import WhatsAppProvider

# Routes an owner/admin/group_admin must still be able to reach even before
# they've set up their mandatory 2FA — everything else is blocked with
# `totp_setup_required` until they do (a freshly-claimed `group_admin`
# account, see `auth/claim_service.py`, has neither factor enabled right
# after claiming, same as a brand-new owner/admin). Matched by exact path
# (after the `/api/v1` prefix FastAPI strips before `request.url.path` is
# read here — see `main.py`'s `api_prefix`), not by prefix, to keep this
# list precise and easy to audit.
#
# Only TOTP's setup/enable routes are listed: the mandatory-2FA gate below is
# satisfied by TOTP *or* WhatsApp-OTP, but every account reaches the
# WhatsApp-OTP setup routes (`/auth/2fa/whatsapp/*`) only via TOTP already
# being enabled first, which by then already satisfies the gate — so those
# routes never need an exemption of their own.
_TOTP_SETUP_EXEMPT_PATHS = {
    "/api/v1/session",
    "/api/v1/auth/logout",
    "/api/v1/auth/2fa/setup",
    "/api/v1/auth/2fa/enable",
}


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
    session signature is still technically valid. Also compares the
    cookie's `token_version` against the user's current one — bumped on
    password change and 2FA enable/disable — so a cookie signed before one
    of those changes is rejected even though its signature is still valid,
    closing the gap a stateless signed cookie would otherwise have (no way
    to revoke a single session server-side).
    """
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise unauthorized()

    decoded = read_session_token(token)
    if decoded is None:
        raise unauthorized()
    user_id, token_version = decoded

    user = db.get(User, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        raise unauthorized()

    if (
        user.role in (UserRole.owner, UserRole.admin, UserRole.group_admin)
        and not (user.totp_enabled or user.whatsapp_otp_enabled)
        and request.url.path not in _TOTP_SETUP_EXEMPT_PATHS
    ):
        raise totp_setup_required()

    return user


def require_role(*roles: UserRole) -> Callable[[User], User]:
    """Dependency factory: `Depends(require_role(UserRole.owner, UserRole.admin))`
    gates a route on the current user's stored `role`, on top of the
    authentication `get_current_user` already performs.

    Kept deliberately narrow — applied only to the specific routes that need
    it (audit log, moderation queue) rather than swept across every endpoint,
    so this doesn't become a breaking-change wave over unrelated routes that
    have never needed role checks before.
    """

    def _check_role(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise forbidden("Your role does not have access to this resource.")
        return user

    return _check_role


def require_group_access() -> Callable[..., User]:
    """Dependency factory reading `group_id` straight from the route's own
    path parameters — composes with (never replaces) `require_role`: this
    answers "which `group_id`," `require_role` still answers "which roles
    may call this route at all." A no-op for owner/admin/viewer; narrows
    `group_admin` to only the group(s) their linked `Member` administers
    (see `authz.py`)."""

    def _check(group_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        ensure_group_access(db, user, group_id)
        return user

    return _check


def require_community_access() -> Callable[..., User]:
    """Same as `require_group_access`, but for routes scoped by
    `community_id`."""

    def _check(
        community_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
    ) -> User:
        ensure_community_access(db, user, community_id)
        return user

    return _check
