"""Pytest fixtures.

`communeer.db` / `communeer.config` read their configuration once, at import
time (module-level `engine`/`SessionLocal`, `lru_cache`d `Settings`). To get
a clean, disposable SQLite file for the whole test session *before* anything
in the `communeer` package is ever imported, the required env vars are set
here at module scope — conftest.py is guaranteed to be imported by pytest
before it collects any test module in this directory.
"""

import os
import tempfile

import pytest
from starlette.testclient import TestClient

_TEST_DB_DIR = tempfile.mkdtemp(prefix="communeer-test-")
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["SESSION_SECRET_KEY"] = "test-secret-key"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["SEED_ADMIN_USERNAME"] = "admin"
os.environ["SEED_ADMIN_PASSWORD"] = "changeme123"
os.environ["WHATSAPP_PROVIDER"] = "mock"
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"

# `auth/security.py`'s module-level `_hasher = PasswordHasher()` uses
# argon2-cffi's default, deliberately expensive (OWASP-recommended)
# parameters — ~120ms per hash/verify on this machine. That's the right
# choice for a real deployment, but the test suite calls it a *lot*: once
# per auto-provisioned `group_admin` account (a placeholder password), once
# per recovery code (10 of them, every single time a test enables 2FA), and
# once per login/verify call across the whole auth test surface — none of
# which need production-strength cost, since these tests only ever check
# hash/verify round-trip correctness, never actual brute-force resistance.
# Swapping in a near-instant hasher here (only within this test session,
# `communeer/auth/security.py` itself is untouched) is what took the full
# suite from ~8.5 minutes to a few tens of seconds. Must be imported after
# the env vars above (so `communeer.auth.security` picks up the test config)
# and before any test module runs.
import argon2

import communeer.auth.security as _security

_security._hasher = argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture()
def db_session(tmp_path):
    """A fresh, independent SQLite database file, isolated from the shared
    app-level test database above — used by tests that exercise
    `sync_community` directly without going through the FastAPI app."""
    import uuid

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from communeer.models import Base

    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="session")
def app():
    """The FastAPI app, imported once (after the env vars above are already
    in place) and shared for the whole test session. Runs migrations + seeds
    the admin user + primes both mock communities exactly once, here,
    directly — not via the app's own ASGI lifespan (see `client` below for
    why that distinction matters)."""
    from communeer.main import _run_migrations, _seed_and_prime_data
    from communeer.main import app as fastapi_app

    _run_migrations()
    _seed_and_prime_data()
    return fastapi_app


@pytest.fixture()
def client(app):
    """A cookie-aware TestClient against the shared test app/database.

    Deliberately NOT entered as a context manager (`with TestClient(app)`):
    doing so re-runs the app's full ASGI lifespan — migrations plus
    re-syncing both mock communities from scratch — on every single call,
    at roughly a second each; with this fixture used by most of the test
    suite, that alone used to account for several minutes of total runtime.
    Routes here never depend on lifespan-time state (`SessionLocal`/`engine`
    in `communeer/db.py` are plain module-level globals set at import time,
    not `app.state`), so a plain instantiation behaves identically for
    request handling while still giving each test its own fresh cookie jar
    (a new `TestClient` instance = a new, empty cookie store)."""
    return TestClient(app)


# Owner/admin accounts now require 2FA to use anything beyond the login/2FA-
# setup routes themselves (see `deps.get_current_user`) — every test that
# logs in as the seeded admin and then calls any other endpoint needs 2FA
# already enabled, or every one of those calls would 428. A fixed secret
# (rather than a randomly generated one) keeps this deterministic and lets
# every test file compute a valid code the same way, without needing to
# share state across the many files that each call this helper.
TEST_ADMIN_TOTP_SECRET = "JBSWY3DPEHPK3PXP"


def _ensure_admin_totp_enabled() -> None:
    import pyotp
    from sqlalchemy import select

    from communeer.auth.security import encrypt_totp_secret
    from communeer.db import SessionLocal
    from communeer.models import User

    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
        if admin is None or admin.totp_enabled:
            return
        admin.totp_secret_encrypted = encrypt_totp_secret(TEST_ADMIN_TOTP_SECRET)
        admin.totp_enabled = True
        db.commit()
    finally:
        db.close()

    # Sanity-check the fixed secret actually produces valid codes under this
    # process's derived Fernet key before any test relies on it.
    assert pyotp.TOTP(TEST_ADMIN_TOTP_SECRET).now()


def login_as_admin(client, *, password: str = "changeme123") -> None:
    """Logs `client` in as the seeded admin, completing the mandatory TOTP
    step. Drop-in replacement for the old one-step `_login(client)` helper
    every test file used to define locally."""
    _ensure_admin_totp_enabled()

    import pyotp

    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    if not body.get("requiresTotp"):
        return  # 2FA wasn't required (e.g. a test rotated it off) — already logged in.

    code = pyotp.TOTP(TEST_ADMIN_TOTP_SECRET).now()
    verify_response = client.post("/api/v1/auth/login/verify-totp", json={"code": code})
    assert verify_response.status_code == 200, verify_response.text
