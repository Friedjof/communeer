import uuid

from sqlalchemy import select

from communeer.auth.security import hash_password, verify_password
from communeer.errors import ApiError
from communeer.models import User, UserRole
from communeer.users.service import (
    create_user,
    list_users,
    reset_user_password,
    update_user,
)

OWNER_ID = uuid.uuid4()


def _seed_owner(db_session, *, username: str = "owner1") -> User:
    user = User(username=username, password_hash=hash_password("whatever123"), role=UserRole.owner, is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_create_user_hashes_password_and_writes_audit_event(db_session):
    owner = _seed_owner(db_session)

    user = create_user(db_session, username="newadmin", password="password123", role=UserRole.admin, actor_user_id=owner.id)

    assert user.username == "newadmin"
    assert user.role == UserRole.admin
    assert user.is_active is True
    assert verify_password("password123", user.password_hash)

    from communeer.models import AuditEvent

    events = list(db_session.execute(select(AuditEvent).where(AuditEvent.action == "user.created")).scalars())
    assert len(events) == 1
    assert events[0].target_id == str(user.id)
    assert "password" not in str(events[0].detail).lower()


def test_create_user_duplicate_username_raises_conflict(db_session):
    owner = _seed_owner(db_session)
    create_user(db_session, username="dupe", password="password123", role=UserRole.admin, actor_user_id=owner.id)

    try:
        create_user(db_session, username="dupe", password="password456", role=UserRole.viewer, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 409


def test_list_users_returns_all(db_session):
    owner = _seed_owner(db_session)
    create_user(db_session, username="second", password="password123", role=UserRole.viewer, actor_user_id=owner.id)

    users = list_users(db_session)
    assert {u.username for u in users} == {owner.username, "second"}


def test_update_user_role_and_active(db_session):
    owner = _seed_owner(db_session)
    target = create_user(db_session, username="target", password="password123", role=UserRole.viewer, actor_user_id=owner.id)

    updated = update_user(db_session, target.id, role=UserRole.admin, is_active=False, actor_user_id=owner.id)

    assert updated.role == UserRole.admin
    assert updated.is_active is False


def test_update_user_unknown_id_raises_not_found(db_session):
    owner = _seed_owner(db_session)
    try:
        update_user(db_session, uuid.uuid4(), role=UserRole.admin, is_active=None, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 404


def test_cannot_deactivate_own_account(db_session):
    owner = _seed_owner(db_session)

    try:
        update_user(db_session, owner.id, role=None, is_active=False, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 409

    db_session.refresh(owner)
    assert owner.is_active is True


def test_cannot_deactivate_the_only_remaining_owner(db_session):
    owner = _seed_owner(db_session)
    admin_actor = create_user(
        db_session, username="second-admin", password="password123", role=UserRole.admin, actor_user_id=owner.id
    )

    try:
        update_user(db_session, owner.id, role=None, is_active=False, actor_user_id=admin_actor.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 409


def test_cannot_demote_the_only_remaining_owner(db_session):
    owner = _seed_owner(db_session)
    admin_actor = create_user(
        db_session, username="second-admin-2", password="password123", role=UserRole.admin, actor_user_id=owner.id
    )

    try:
        update_user(db_session, owner.id, role=UserRole.admin, is_active=None, actor_user_id=admin_actor.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 409


def test_can_deactivate_owner_when_a_second_owner_exists(db_session):
    owner = _seed_owner(db_session)
    second_owner = create_user(
        db_session, username="second-owner", password="password123", role=UserRole.owner, actor_user_id=owner.id
    )

    updated = update_user(db_session, owner.id, role=None, is_active=False, actor_user_id=second_owner.id)
    assert updated.is_active is False


def test_reset_user_password_updates_hash_and_writes_audit_event(db_session):
    owner = _seed_owner(db_session)
    target = create_user(db_session, username="resettarget", password="password123", role=UserRole.viewer, actor_user_id=owner.id)

    reset_user_password(db_session, target.id, new_password="brandnewpass123", actor_user_id=owner.id)

    db_session.refresh(target)
    assert verify_password("brandnewpass123", target.password_hash)
    assert not verify_password("password123", target.password_hash)


# ---------------------------------------------------------------------------
# HTTP-level: owner-only gating
# ---------------------------------------------------------------------------


def _login(client) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "changeme123"})
    assert response.status_code == 200


def _seed_admin_role_user() -> None:
    from communeer.db import SessionLocal

    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.username == "plain-admin")).scalar_one_or_none()
        if existing is not None:
            return
        db.add(
            User(
                username="plain-admin",
                password_hash=hash_password("plain-admin-pw-123"),
                role=UserRole.admin,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()


def test_users_route_requires_owner_role(client):
    _seed_admin_role_user()
    client.post("/api/v1/auth/login", json={"username": "plain-admin", "password": "plain-admin-pw-123"})

    response = client.get("/api/v1/users")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    client.post("/api/v1/auth/logout")
    _login(client)


def test_users_crud_end_to_end_as_owner(client):
    _login(client)

    create_response = client.post(
        "/api/v1/users", json={"username": "e2e-user", "password": "password12345", "role": "viewer"}
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["username"] == "e2e-user"
    assert created["isActive"] is True

    list_response = client.get("/api/v1/users")
    assert any(u["username"] == "e2e-user" for u in list_response.json())

    patch_response = client.patch(f"/api/v1/users/{created['id']}", json={"role": "admin"})
    assert patch_response.status_code == 200
    assert patch_response.json()["role"] == "admin"

    reset_response = client.post(f"/api/v1/users/{created['id']}/reset-password", json={"password": "newpassword123"})
    assert reset_response.status_code == 204
