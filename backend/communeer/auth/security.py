"""Password hashing (Argon2id) and the signed session cookie.

No JWT, no server-side session store: a single admin user doesn't need
either. The cookie payload is just `{"uid": "<user-id>"}`, signed with
`itsdangerous` so it can't be forged or tampered with; `deps.get_current_user`
still re-loads the `User` row from the DB on every request so a deactivated
user is rejected even with a still-validly-signed cookie.
"""

import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from communeer.config import get_settings

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.session_secret_key, salt="communeer-session")


def create_session_token(user_id: uuid.UUID) -> str:
    return _serializer().dumps({"uid": str(user_id)})


def read_session_token(token: str) -> uuid.UUID | None:
    """Return the user id encoded in `token`, or `None` if it's missing,
    malformed, tampered with, or expired."""
    settings = get_settings()
    try:
        payload = _serializer().loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    raw_uid = payload.get("uid")
    if raw_uid is None:
        return None
    try:
        return uuid.UUID(raw_uid)
    except (ValueError, TypeError):
        return None
