"""WhatsApp-OTP: a second, independent 2FA factor alongside TOTP (see
`auth/service.py`'s WhatsApp-OTP section). Setup/enable/disable, login with
WhatsApp-OTP only and with both factors enabled, the shared lockout counter,
the "recovery codes survive as long as one factor remains" rule, resend
cooldown, and provider-unavailable handling.

Never touches the shared `admin` user's 2FA state — same isolation
convention as `test_auth_2fa.py`. Every test in this file creates its own
dedicated user.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
from sqlalchemy import select
from starlette.testclient import TestClient

from communeer.auth.phone import normalize_phone_to_wa_id
from communeer.auth.security import (
    PENDING_2FA_MAX_AGE_SECONDS,
    WHATSAPP_OTP_RESEND_COOLDOWN_SECONDS,
    encrypt_totp_secret,
    hash_password,
)
from communeer.db import SessionLocal
from communeer.models import User, UserRecoveryCode, UserRole
from communeer.providers.whatsapp import get_provider
from communeer.providers.whatsapp.base import WhatsAppNotConnectedError

TEST_PHONE = "+49 151 23456789"
TEST_PHONE_WA_ID = "4915123456789@c.us"


def _create_user(
    *,
    username: str,
    password: str,
    role: UserRole,
    totp_secret: str | None = None,
    whatsapp_otp_phone: str | None = None,
) -> uuid.UUID:
    db = SessionLocal()
    try:
        user = User(username=username, password_hash=hash_password(password), role=role, is_active=True)
        if totp_secret is not None:
            user.totp_enabled = True
            user.totp_secret_encrypted = encrypt_totp_secret(totp_secret)
        if whatsapp_otp_phone is not None:
            user.whatsapp_otp_enabled = True
            user.phone_wa_id = normalize_phone_to_wa_id(whatsapp_otp_phone)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def _unique_username(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _last_sent_otp_code() -> str:
    provider = get_provider()
    _member_wa_id, message = provider._sent_messages[-1]
    match = re.search(r"\b(\d{6})\b", message)
    assert match is not None, f"no 6-digit code found in sent message: {message!r}"
    return match.group(1)


def _backdate_pending_otp(username: str, *, seconds_ago: float) -> None:
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.username == username)).scalar_one()
        user.pending_otp_sent_at = datetime.now(UTC) - timedelta(seconds=seconds_ago)
        db.commit()
    finally:
        db.close()


def _login_password_step(client, username: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Setup / enable (second factor, TOTP already enabled first — the only
# reachable ordering, since `/auth/2fa/whatsapp/setup` isn't in the
# mandatory-2FA gate's exempt list, see `deps.py`)
# ---------------------------------------------------------------------------


def test_setup_then_enable_flow(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    user_id = _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)
    # `_create_user(totp_secret=...)` bypasses the real `/auth/2fa/enable`
    # ceremony (which always generates a fresh set) — insert one directly to
    # simulate "this account already has a valid set from its first factor."
    db = SessionLocal()
    try:
        db.add(UserRecoveryCode(user_id=user_id, code_hash=hash_password("existing-code-0000")))
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})

    setup_response = client.post("/api/v1/auth/2fa/whatsapp/setup", json={"phoneNumber": TEST_PHONE})
    assert setup_response.status_code == 200, setup_response.text
    assert setup_response.json()["phoneWaId"] == TEST_PHONE_WA_ID

    code = _last_sent_otp_code()
    enable_response = client.post("/api/v1/auth/2fa/whatsapp/enable", json={"code": code})
    assert enable_response.status_code == 200, enable_response.text
    # An existing valid set — adding a second factor shouldn't invalidate
    # codes the user already saved.
    assert enable_response.json()["recoveryCodes"] is None

    session_response = client.get("/api/v1/session")
    assert session_response.json()["whatsappOtpEnabled"] is True


def test_enable_generates_fresh_codes_when_none_exist(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})
    client.post("/api/v1/auth/2fa/whatsapp/setup", json={"phoneNumber": TEST_PHONE})
    code = _last_sent_otp_code()

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.username == username)).scalar_one()
        db.execute(UserRecoveryCode.__table__.delete().where(UserRecoveryCode.user_id == user.id))
        db.commit()
    finally:
        db.close()

    enable_response = client.post("/api/v1/auth/2fa/whatsapp/enable", json={"code": code})
    assert enable_response.status_code == 200, enable_response.text
    codes = enable_response.json()["recoveryCodes"]
    assert codes is not None
    assert len(codes) == 10
    assert len(set(codes)) == 10


def test_enable_rejects_wrong_code(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})
    client.post("/api/v1/auth/2fa/whatsapp/setup", json={"phoneNumber": TEST_PHONE})

    response = client.post("/api/v1/auth/2fa/whatsapp/enable", json={"code": "000000"})
    assert response.status_code == 400


def test_enable_rejects_expired_code(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})
    client.post("/api/v1/auth/2fa/whatsapp/setup", json={"phoneNumber": TEST_PHONE})
    code = _last_sent_otp_code()

    _backdate_pending_otp(username, seconds_ago=PENDING_2FA_MAX_AGE_SECONDS + 5)

    response = client.post("/api/v1/auth/2fa/whatsapp/enable", json={"code": code})
    assert response.status_code == 400


def test_setup_enforces_resend_cooldown(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})

    first = client.post("/api/v1/auth/2fa/whatsapp/setup", json={"phoneNumber": TEST_PHONE})
    assert first.status_code == 200

    second = client.post("/api/v1/auth/2fa/whatsapp/setup", json={"phoneNumber": TEST_PHONE})
    assert second.status_code == 429

    _backdate_pending_otp(username, seconds_ago=WHATSAPP_OTP_RESEND_COOLDOWN_SECONDS + 1)

    third = client.post("/api/v1/auth/2fa/whatsapp/setup", json={"phoneNumber": TEST_PHONE})
    assert third.status_code == 200


def test_setup_rejects_when_already_enabled(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(
        username=username,
        password="password12345",
        role=UserRole.owner,
        totp_secret=secret,
        whatsapp_otp_phone=TEST_PHONE,
    )

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})

    response = client.post("/api/v1/auth/2fa/whatsapp/setup", json={"phoneNumber": TEST_PHONE})
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Disable + the "recovery codes survive as long as one factor remains" rule
# ---------------------------------------------------------------------------


def test_disabling_totp_first_keeps_recovery_codes_while_whatsapp_otp_remains(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    user_id = _create_user(
        username=username,
        password="password12345",
        role=UserRole.owner,
        totp_secret=secret,
        whatsapp_otp_phone=TEST_PHONE,
    )
    db = SessionLocal()
    try:
        db.add(UserRecoveryCode(user_id=user_id, code_hash=hash_password("aaaa1111-bbbb2222")))
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})

    disable_response = client.post("/api/v1/auth/2fa/disable", json={"password": "password12345"})
    assert disable_response.status_code == 204

    db = SessionLocal()
    try:
        remaining = db.execute(
            select(UserRecoveryCode).where(UserRecoveryCode.user_id == user_id)
        ).scalars().all()
        assert len(remaining) == 1  # untouched — WhatsApp-OTP is still enabled

        user = db.get(User, user_id)
        assert user.whatsapp_otp_enabled is True
    finally:
        db.close()

    disable_whatsapp_response = client.post("/api/v1/auth/2fa/whatsapp/disable", json={"password": "password12345"})
    assert disable_whatsapp_response.status_code == 204

    db = SessionLocal()
    try:
        remaining = db.execute(
            select(UserRecoveryCode).where(UserRecoveryCode.user_id == user_id)
        ).scalars().all()
        assert remaining == []  # now wiped — no factor left enabled
    finally:
        db.close()


def test_disabling_whatsapp_otp_first_keeps_recovery_codes_while_totp_remains(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    user_id = _create_user(
        username=username,
        password="password12345",
        role=UserRole.owner,
        totp_secret=secret,
        whatsapp_otp_phone=TEST_PHONE,
    )
    db = SessionLocal()
    try:
        db.add(UserRecoveryCode(user_id=user_id, code_hash=hash_password("aaaa1111-bbbb2222")))
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})

    disable_whatsapp_response = client.post("/api/v1/auth/2fa/whatsapp/disable", json={"password": "password12345"})
    assert disable_whatsapp_response.status_code == 204

    db = SessionLocal()
    try:
        remaining = db.execute(
            select(UserRecoveryCode).where(UserRecoveryCode.user_id == user_id)
        ).scalars().all()
        assert len(remaining) == 1  # untouched — TOTP is still enabled
    finally:
        db.close()

    disable_totp_response = client.post("/api/v1/auth/2fa/disable", json={"password": "password12345"})
    assert disable_totp_response.status_code == 204

    db = SessionLocal()
    try:
        remaining = db.execute(
            select(UserRecoveryCode).where(UserRecoveryCode.user_id == user_id)
        ).scalars().all()
        assert remaining == []  # now wiped — no factor left enabled
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_with_whatsapp_otp_only(client, app):
    username = _unique_username("owner")
    _create_user(username=username, password="password12345", role=UserRole.owner, whatsapp_otp_phone=TEST_PHONE)

    fresh_client = TestClient(app)
    login_body = _login_password_step(fresh_client, username, "password12345")
    assert login_body["requiresTotp"] is True
    assert login_body["totpEnabled"] is False
    assert login_body["whatsappOtpEnabled"] is True

    request_response = fresh_client.post("/api/v1/auth/login/whatsapp-otp/request")
    assert request_response.status_code == 204

    code = _last_sent_otp_code()
    verify_response = fresh_client.post("/api/v1/auth/login/whatsapp-otp/verify", json={"code": code})
    assert verify_response.status_code == 200
    assert "communeer_session" in fresh_client.cookies


def test_login_with_both_factors_enabled_reports_both(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(
        username=username,
        password="password12345",
        role=UserRole.owner,
        totp_secret=secret,
        whatsapp_otp_phone=TEST_PHONE,
    )

    login_body = _login_password_step(client, username, "password12345")
    assert login_body["requiresTotp"] is True
    assert login_body["totpEnabled"] is True
    assert login_body["whatsappOtpEnabled"] is True


def test_lockout_counter_shared_across_totp_and_whatsapp_otp_login_steps(client, app):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(
        username=username,
        password="password12345",
        role=UserRole.owner,
        totp_secret=secret,
        whatsapp_otp_phone=TEST_PHONE,
    )

    fresh_client = TestClient(app)
    _login_password_step(fresh_client, username, "password12345")
    fresh_client.post("/api/v1/auth/login/whatsapp-otp/request")

    # 3 wrong TOTP guesses + 2 wrong WhatsApp-OTP guesses = 5 total failures.
    for _ in range(3):
        response = fresh_client.post("/api/v1/auth/login/verify-totp", json={"code": "000000"})
        assert response.status_code == 401
    for _ in range(2):
        response = fresh_client.post("/api/v1/auth/login/whatsapp-otp/verify", json={"code": "000000"})
        assert response.status_code == 401

    # The 6th failure of *either* kind is locked out.
    locked_response = fresh_client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})
    assert locked_response.status_code == 429


# ---------------------------------------------------------------------------
# Provider-unavailable handling
# ---------------------------------------------------------------------------


def test_setup_returns_503_when_provider_unavailable(client, monkeypatch):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})

    provider = get_provider()

    def _raise_not_connected(*args, **kwargs):
        raise WhatsAppNotConnectedError("disconnected")

    monkeypatch.setattr(provider, "send_text_message", _raise_not_connected)

    response = client.post("/api/v1/auth/2fa/whatsapp/setup", json={"phoneNumber": TEST_PHONE})
    assert response.status_code == 503


def test_login_request_returns_503_when_provider_unavailable(client, monkeypatch, app):
    username = _unique_username("owner")
    _create_user(username=username, password="password12345", role=UserRole.owner, whatsapp_otp_phone=TEST_PHONE)

    fresh_client = TestClient(app)
    _login_password_step(fresh_client, username, "password12345")

    provider = get_provider()

    def _raise_not_connected(*args, **kwargs):
        raise WhatsAppNotConnectedError("disconnected")

    monkeypatch.setattr(provider, "send_text_message", _raise_not_connected)

    response = fresh_client.post("/api/v1/auth/login/whatsapp-otp/request")
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Phone number normalization
# ---------------------------------------------------------------------------


def test_normalize_phone_to_wa_id_strips_formatting():
    assert normalize_phone_to_wa_id("+49 151 23456789") == "4915123456789@c.us"
    assert normalize_phone_to_wa_id("(030) 12345678") == "03012345678@c.us"


def test_normalize_phone_to_wa_id_rejects_too_short():
    from communeer.errors import ApiError

    try:
        normalize_phone_to_wa_id("123")
        raised = False
    except ApiError:
        raised = True
    assert raised


def test_normalize_phone_to_wa_id_rejects_too_long():
    from communeer.errors import ApiError

    try:
        normalize_phone_to_wa_id("1" * 20)
        raised = False
    except ApiError:
        raised = True
    assert raised


def test_normalize_phone_to_wa_id_rejects_garbage():
    from communeer.errors import ApiError

    try:
        normalize_phone_to_wa_id("not a phone number")
        raised = False
    except ApiError:
        raised = True
    assert raised
