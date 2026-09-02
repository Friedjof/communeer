"""TOTP two-factor auth: setup/enable, two-step login, recovery codes,
shared login lockout, session invalidation via `token_version`, and the
owner-only `/users/{id}/reset-2fa` recovery path.

Never touches the shared `admin` user's 2FA state here — every other test
file's `_login`/`login_as_admin` helper depends on `admin` staying
`totp_enabled=True` for the rest of the session (see `conftest.py`). Every
test in this file creates its own dedicated user instead.
"""

import uuid

import pyotp
from sqlalchemy import select
from starlette.testclient import TestClient

from communeer.auth.security import encrypt_totp_secret, hash_password
from communeer.db import SessionLocal
from communeer.models import User, UserRecoveryCode, UserRole
from tests.conftest import login_as_admin


def _create_user(*, username: str, password: str, role: UserRole, totp_secret: str | None = None) -> uuid.UUID:
    db = SessionLocal()
    try:
        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        if totp_secret is not None:
            user.totp_enabled = True
            user.totp_secret_encrypted = encrypt_totp_secret(totp_secret)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def _unique_username(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Setup / enable
# ---------------------------------------------------------------------------


def test_setup_then_enable_flow(client):
    username = _unique_username("owner")
    _create_user(username=username, password="password12345", role=UserRole.owner)

    login_response = client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    assert login_response.status_code == 200
    # No 2FA set up yet — a one-step login, so the response is a full
    # `UserOut`, not a `{requiresTotp: true}` marker.
    assert "requiresTotp" not in login_response.json()
    assert "communeer_session" in client.cookies

    # Not yet enrolled: every route except the exempt setup/session ones 428s.
    assert client.get("/api/v1/communities").status_code == 428
    assert client.get("/api/v1/session").status_code == 200
    assert client.get("/api/v1/communities").json()["error"]["code"] == "totp_setup_required"

    setup_response = client.post("/api/v1/auth/2fa/setup")
    assert setup_response.status_code == 200
    setup_body = setup_response.json()
    secret = setup_body["secret"]
    assert setup_body["otpauthUri"].startswith("otpauth://totp/")
    assert username in setup_body["otpauthUri"]

    # A wrong code doesn't enable it.
    wrong_response = client.post("/api/v1/auth/2fa/enable", json={"code": "000000"})
    assert wrong_response.status_code == 400
    assert client.get("/api/v1/session").json()["totpEnabled"] is False

    code = pyotp.TOTP(secret).now()
    enable_response = client.post("/api/v1/auth/2fa/enable", json={"code": code})
    assert enable_response.status_code == 200
    recovery_codes = enable_response.json()["recoveryCodes"]
    assert len(recovery_codes) == 10
    assert len(set(recovery_codes)) == 10  # all distinct

    # Enrolled now — the 428 gate is gone, and the session survived the
    # `token_version` bump `enable_totp` does internally.
    assert client.get("/api/v1/session").json()["totpEnabled"] is True
    assert client.get("/api/v1/communities").status_code == 200


def test_setup_rejects_when_already_enabled(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    login_response = client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    assert login_response.json()["requiresTotp"] is True
    verify_response = client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})
    assert verify_response.status_code == 200

    assert client.post("/api/v1/auth/2fa/setup").status_code == 409


# ---------------------------------------------------------------------------
# Two-step login + recovery codes
# ---------------------------------------------------------------------------


def test_login_with_totp_two_step_flow(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    password_response = client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    assert password_response.status_code == 200
    assert password_response.json()["requiresTotp"] is True
    assert "communeer_session" not in client.cookies

    wrong_code_response = client.post("/api/v1/auth/login/verify-totp", json={"code": "000000"})
    assert wrong_code_response.status_code == 401
    assert "communeer_session" not in client.cookies

    ok_response = client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})
    assert ok_response.status_code == 200
    assert ok_response.json()["username"] == username
    assert "communeer_session" in client.cookies


def test_recovery_code_login_is_single_use(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.username == username)).scalar_one()
        db.add(UserRecoveryCode(user_id=user.id, code_hash=hash_password("aaaa1111-bbbb2222")))
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    first = client.post("/api/v1/auth/login/verify-totp", json={"code": "aaaa1111-bbbb2222"})
    assert first.status_code == 200
    client.post("/api/v1/auth/logout")

    # The same recovery code doesn't work a second time.
    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    second = client.post("/api/v1/auth/login/verify-totp", json={"code": "aaaa1111-bbbb2222"})
    assert second.status_code == 401


def test_regenerating_recovery_codes_invalidates_the_old_set(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.username == username)).scalar_one()
        db.add(UserRecoveryCode(user_id=user.id, code_hash=hash_password("old-code-1234")))
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})

    regenerate_response = client.post(
        "/api/v1/auth/2fa/recovery-codes/regenerate", json={"password": "password12345"}
    )
    assert regenerate_response.status_code == 200
    new_codes = regenerate_response.json()["recoveryCodes"]
    assert "old-code-1234" not in new_codes

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    old_code_response = client.post("/api/v1/auth/login/verify-totp", json={"code": "old-code-1234"})
    assert old_code_response.status_code == 401


def test_disable_requires_password_not_a_code(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})

    wrong_password = client.post("/api/v1/auth/2fa/disable", json={"password": "not-the-password"})
    assert wrong_password.status_code == 400
    assert client.get("/api/v1/session").json()["totpEnabled"] is True

    ok = client.post("/api/v1/auth/2fa/disable", json={"password": "password12345"})
    assert ok.status_code == 204
    assert client.get("/api/v1/session").json()["totpEnabled"] is False

    # Disabling bumps `token_version` but reissues a fresh cookie for this
    # same request/session (matching `enable_totp`) — this owner immediately
    # falls back under the mandatory-2FA gate rather than being logged out,
    # since their role still requires it.
    assert client.get("/api/v1/communities").status_code == 428


def test_disabling_totp_does_not_wipe_recovery_codes_when_whatsapp_otp_remains_enabled(client):
    """Regression test for the behavior change `auth/service.py`'s
    WhatsApp-OTP support introduced: recovery codes are a generic backup for
    "any 2FA factor," not TOTP-specific — disabling TOTP alone must not wipe
    them while a second factor (WhatsApp-OTP) is still active. See
    `test_auth_whatsapp_otp.py` for the full disable/recovery-code matrix."""
    from communeer.auth.phone import normalize_phone_to_wa_id
    from communeer.models import User, UserRecoveryCode

    username = _unique_username("owner")
    secret = pyotp.random_base32()
    user_id = _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        user.whatsapp_otp_enabled = True
        user.phone_wa_id = normalize_phone_to_wa_id("+49 151 23456789")
        db.add(UserRecoveryCode(user_id=user_id, code_hash=hash_password("aaaa1111-bbbb2222")))
        db.commit()
    finally:
        db.close()

    client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})

    response = client.post("/api/v1/auth/2fa/disable", json={"password": "password12345"})
    assert response.status_code == 204

    db = SessionLocal()
    try:
        remaining = db.execute(select(UserRecoveryCode).where(UserRecoveryCode.user_id == user_id)).scalars().all()
        assert len(remaining) == 1
    finally:
        db.close()

    # WhatsApp-OTP is still enabled, so the mandatory-2FA gate is satisfied —
    # no 428, unlike the TOTP-only case above.
    assert client.get("/api/v1/communities").status_code != 428


# ---------------------------------------------------------------------------
# Login lockout, shared between the password and TOTP steps
# ---------------------------------------------------------------------------


def test_lockout_after_repeated_failed_passwords(client):
    username = _unique_username("viewer")
    _create_user(username=username, password="password12345", role=UserRole.viewer)

    for _ in range(5):
        response = client.post("/api/v1/auth/login", json={"username": username, "password": "wrong"})
        assert response.status_code == 401

    locked_response = client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    assert locked_response.status_code == 429
    assert locked_response.json()["error"]["code"] == "too_many_requests"


def test_lockout_counter_is_shared_across_password_and_totp_steps(client):
    username = _unique_username("owner")
    secret = pyotp.random_base32()
    _create_user(username=username, password="password12345", role=UserRole.owner, totp_secret=secret)

    # 3 wrong passwords, then get a valid pending-2FA cookie, then 2 wrong
    # codes — 5 total failures should trip the same counter.
    for _ in range(3):
        assert client.post(
            "/api/v1/auth/login", json={"username": username, "password": "wrong"}
        ).status_code == 401

    password_response = client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    assert password_response.status_code == 200
    assert password_response.json()["requiresTotp"] is True

    for _ in range(2):
        assert client.post("/api/v1/auth/login/verify-totp", json={"code": "000000"}).status_code == 401

    locked_response = client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(secret).now()})
    assert locked_response.status_code == 429


# ---------------------------------------------------------------------------
# token_version session invalidation
# ---------------------------------------------------------------------------


def test_password_change_invalidates_other_sessions(client, app):
    """Simulates two browsers: `client` is the one whose password gets
    changed via the owner-only reset-password route; `other_client` holds an
    older session cookie signed before that change."""
    username = _unique_username("viewer")
    user_id = _create_user(username=username, password="password12345", role=UserRole.viewer)

    other_client = TestClient(app)
    other_client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    assert other_client.get("/api/v1/session").status_code == 200

    login_as_admin(client)
    reset_response = client.post(f"/api/v1/users/{user_id}/reset-password", json={"password": "newpassword123"})
    assert reset_response.status_code == 204

    # The old cookie's `token_version` no longer matches — rejected even
    # though its signature is still perfectly valid.
    assert other_client.get("/api/v1/session").status_code == 401


def test_role_change_invalidates_other_sessions(client, app):
    username = _unique_username("viewer")
    user_id = _create_user(username=username, password="password12345", role=UserRole.viewer)

    other_client = TestClient(app)
    other_client.post("/api/v1/auth/login", json={"username": username, "password": "password12345"})
    assert other_client.get("/api/v1/session").status_code == 200

    login_as_admin(client)
    patch_response = client.patch(f"/api/v1/users/{user_id}", json={"role": "admin"})
    assert patch_response.status_code == 200

    assert other_client.get("/api/v1/session").status_code == 401


# ---------------------------------------------------------------------------
# Owner-only reset-2fa recovery path
# ---------------------------------------------------------------------------


def test_owner_can_reset_a_locked_out_teammates_2fa(client, app):
    username = _unique_username("admin")
    secret = pyotp.random_base32()
    user_id = _create_user(username=username, password="password12345", role=UserRole.admin, totp_secret=secret)

    login_as_admin(client)
    reset_response = client.post(f"/api/v1/users/{user_id}/reset-2fa")
    assert reset_response.status_code == 204

    # Logging in as the reset teammate is a one-step flow again, and they're
    # routed straight back into the mandatory-setup gate.
    other_client = TestClient(app)
    login_response = other_client.post(
        "/api/v1/auth/login", json={"username": username, "password": "password12345"}
    )
    assert login_response.status_code == 200
    assert "requiresTotp" not in login_response.json()  # one-step login again
    assert other_client.get("/api/v1/communities").status_code == 428


def test_reset_2fa_requires_owner_role(client):
    admin_username = _unique_username("admin")
    admin_secret = pyotp.random_base32()
    _create_user(username=admin_username, password="password12345", role=UserRole.admin, totp_secret=admin_secret)
    target_username = _unique_username("viewer")
    target_id = _create_user(username=target_username, password="password12345", role=UserRole.viewer)

    client.post("/api/v1/auth/login", json={"username": admin_username, "password": "password12345"})
    client.post("/api/v1/auth/login/verify-totp", json={"code": pyotp.TOTP(admin_secret).now()})

    response = client.post(f"/api/v1/users/{target_id}/reset-2fa")
    assert response.status_code == 403
