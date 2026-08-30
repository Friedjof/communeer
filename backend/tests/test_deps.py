"""Isolated unit tests for `require_role`, independent of the full app/DB —
a tiny standalone FastAPI app with `get_current_user` overridden to return a
fake user of a given role, so these tests exercise only the role-gating
logic itself (401/403 shaping is already covered end-to-end for the real
`/audit` and `/moderation/queue` routes elsewhere)."""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from communeer.deps import get_current_user, require_role
from communeer.errors import register_exception_handlers
from communeer.models import User, UserRole


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/owner-or-admin", dependencies=[Depends(require_role(UserRole.owner, UserRole.admin))])
    def _owner_or_admin() -> dict:
        return {"ok": True}

    @app.get("/owner-only", dependencies=[Depends(require_role(UserRole.owner))])
    def _owner_only() -> dict:
        return {"ok": True}

    return app


def _fake_user(role: UserRole) -> User:
    return User(username="fake", password_hash="x", role=role, is_active=True)


def _client_as(role: UserRole) -> TestClient:
    app = _make_app()
    app.dependency_overrides[get_current_user] = lambda: _fake_user(role)
    return TestClient(app)


def test_viewer_gets_403_on_owner_or_admin_route():
    client = _client_as(UserRole.viewer)
    response = client.get("/owner-or-admin")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_admin_gets_200_on_owner_or_admin_route():
    client = _client_as(UserRole.admin)
    response = client.get("/owner-or-admin")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_owner_gets_200_on_owner_or_admin_route():
    client = _client_as(UserRole.owner)
    response = client.get("/owner-or-admin")
    assert response.status_code == 200


def test_admin_gets_403_on_owner_only_route():
    client = _client_as(UserRole.admin)
    response = client.get("/owner-only")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_unauthenticated_request_still_401s_before_role_check():
    """`require_role` layers on top of `get_current_user`, so a request with
    no session at all must still 401 (not 403) — the real app's own
    `get_current_user` runs unmodified here (no override installed)."""
    app = _make_app()
    client = TestClient(app)
    response = client.get("/owner-or-admin")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
