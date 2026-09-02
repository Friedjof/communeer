"""Password hashing (Argon2id), TOTP two-factor auth, and signed cookies
(full session + short-lived pending-2FA).

No JWT, no server-side session store — the full-session cookie payload is
`{"uid": "<user-id>", "tv": <token_version>}`, signed with `itsdangerous` so
it can't be forged or tampered with. `deps.get_current_user` re-loads the
`User` row from the DB on every request (so a deactivated user is rejected
even with a still-validly-signed cookie) and compares `tv` against the
user's current `token_version`, which is bumped on password change, role
change, and 2FA enable/disable — this is what lets those actions invalidate
any cookie signed before them, without needing a server-side session store.
"""

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from communeer.config import get_settings

_hasher = PasswordHasher()

# How long a "password step passed, waiting for a second-factor code" cookie
# stays valid — short on purpose, this is a narrow window between two steps
# of one login attempt, not a session. Shared by both 2FA factors (TOTP and
# WhatsApp-OTP): also used as the validity window for a WhatsApp-OTP code
# (setup- or login-time) so a code is never valid for longer than the cookie
# that carries the login attempt it belongs to.
PENDING_2FA_MAX_AGE_SECONDS = 5 * 60

# Minimum time between two WhatsApp-OTP sends to the same user (setup or
# login) — WhatsApp messaging isn't free/instant like a TOTP code, so resend
# spam needs its own throttle independent of the shared lockout counter
# below (which only limits wrong *verify* attempts, not send requests).
WHATSAPP_OTP_RESEND_COOLDOWN_SECONDS = 30


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False


def _serializer(salt: str) -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.session_secret_key, salt=salt)


def create_session_token(user_id: uuid.UUID, token_version: int) -> str:
    return _serializer("communeer-session").dumps({"uid": str(user_id), "tv": token_version})


def read_session_token(token: str) -> tuple[uuid.UUID, int] | None:
    """Return `(user_id, token_version)` encoded in `token`, or `None` if
    it's missing, malformed, tampered with, or expired."""
    settings = get_settings()
    try:
        payload = _serializer("communeer-session").loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    raw_uid = payload.get("uid")
    raw_tv = payload.get("tv")
    if raw_uid is None or not isinstance(raw_tv, int):
        return None
    try:
        return uuid.UUID(raw_uid), raw_tv
    except (ValueError, TypeError):
        return None


def create_pending_2fa_token(user_id: uuid.UUID) -> str:
    """A short-lived, separately-salted token proving "the password step of
    login just succeeded for this user" — issued instead of a full session
    cookie when the user has a 2FA factor enabled (TOTP and/or WhatsApp-OTP),
    exchanged for a real session via `/auth/login/verify-totp` or
    `/auth/login/whatsapp-otp/verify`. Deliberately not a full session token:
    it can't be used to call any authenticated route."""
    return _serializer("communeer-2fa-pending").dumps({"uid": str(user_id)})


def read_pending_2fa_token(token: str) -> uuid.UUID | None:
    try:
        payload = _serializer("communeer-2fa-pending").loads(token, max_age=PENDING_2FA_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    raw_uid = payload.get("uid")
    if raw_uid is None:
        return None
    try:
        return uuid.UUID(raw_uid)
    except (ValueError, TypeError):
        return None


# -- TOTP secret generation/verification ---------------------------------


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(secret: str, username: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="Communeer")


def verify_totp_code(secret: str, code: str) -> bool:
    """`valid_window=1` tolerates the authenticator app's clock being up to
    one 30s step ahead or behind the server's."""
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)


# -- TOTP secret encryption at rest ---------------------------------------
# A TOTP secret must be *readable* server-side to verify a code, so (unlike
# `password_hash`) it can't be a one-way hash. Encrypted instead, with a key
# derived from `session_secret_key` via a distinct context string — this
# avoids needing a third secret to configure/rotate while keeping the
# derived key cryptographically separate from the cookie-signing key.


def _fernet() -> Fernet:
    settings = get_settings()
    digest = hashlib.sha256(f"totp-encryption:{settings.session_secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_totp_secret(token: str) -> str | None:
    """`None` if the ciphertext can't be decrypted (e.g. `session_secret_key`
    was rotated after this secret was encrypted) — callers treat this the
    same as "no 2FA configured" rather than raising."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


# -- Recovery codes --------------------------------------------------------
# Hashed at rest exactly like a password (via `hash_password`/
# `verify_password` above) — never stored in plaintext, since each code is
# itself a valid login credential.


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]


# -- WhatsApp-OTP (second, independent 2FA factor) --------------------------
# A short-lived numeric code delivered via a WhatsApp DM (see
# `WhatsAppProvider.send_text_message`) instead of read off an authenticator
# app. Hashed at rest exactly like a recovery code (via `hash_password`/
# `verify_password` above) — no separate crypto scheme needed for a 6-digit
# space, since the shared lockout counter (`is_locked_out` below) already
# does the real rate-limiting work on guesses.


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def build_whatsapp_otp_message(code: str) -> str:
    return (
        f"Dein Communeer-Anmeldecode ist {code}. Er läuft in 5 Minuten ab. "
        "Teile diesen Code mit niemandem.\n\n"
        f"Hi! Your Communeer login code is {code}. It expires in 5 minutes. "
        "Never share this code with anyone."
    )


# -- Login brute-force lockout ---------------------------------------------


def is_locked_out(locked_until: datetime | None, *, now: datetime) -> bool:
    if locked_until is None:
        return False
    # SQLite drops tzinfo on round-trip: a `DateTime(timezone=True)` value
    # written as UTC-aware comes back naive from a fresh query (same
    # workaround as `renewals/service.py`'s `_ensure_utc`).
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    return now < locked_until
