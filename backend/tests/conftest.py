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
    in place) and shared for the whole test session — its lifespan runs
    migrations + seeds the admin user + primes both mock communities."""
    from communeer.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client(app):
    """A cookie-aware TestClient against the shared test app/database."""
    with TestClient(app) as test_client:
        yield test_client
