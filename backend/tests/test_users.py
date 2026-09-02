import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from communeer.auth.security import hash_password, verify_password
from communeer.errors import ApiError
from communeer.models import Member, User, UserRole
from communeer.models.base import new_uuid
from communeer.providers.whatsapp.base import WhatsAppProviderUnavailableError
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.users.service import (
    approve_group_admin,
    create_user,
    list_users,
    resend_claim_code,
    reset_user_password,
    update_user,
)
from tests.conftest import login_as_admin as _login

OWNER_ID = uuid.uuid4()


def _seed_unclaimed_group_admin(
    db_session, *, username: str = "unclaimed-admin", is_approved: bool = False
) -> User:
    """`is_approved=False` by default — matches what real auto-provisioning
    actually produces (see `auth/provisioning.py`'s module docstring); pass
    `is_approved=True` for tests exercising what happens *after* approval
    (e.g. `resend_claim_code`)."""
    member = Member(
        id=new_uuid(),
        wa_id=f"4915{uuid.uuid4().int % 10**9}@c.us",
        display_name="Unclaimed Admin",
        first_seen_at=datetime.now(UTC),
    )
    db_session.add(member)
    db_session.flush()

    user = User(
        username=username,
        password_hash=hash_password(uuid.uuid4().hex),
        role=UserRole.group_admin,
        is_active=True,
        is_claimed=False,
        is_approved=is_approved,
        member_id=member.id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class _FailingSendProvider(MockWhatsAppProvider):
    def send_text_message(self, member_wa_id: str, message: str) -> str | None:
        raise WhatsAppProviderUnavailableError("boom")


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
# group_admin: only ever auto-provisioned, never assignable by hand
# ---------------------------------------------------------------------------


def test_create_user_rejects_group_admin_role(db_session):
    owner = _seed_owner(db_session)

    try:
        create_user(db_session, username="wannabe", password="password123", role=UserRole.group_admin, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 400

    assert db_session.execute(select(User).where(User.username == "wannabe")).scalar_one_or_none() is None


def test_update_user_rejects_assigning_group_admin_role(db_session):
    owner = _seed_owner(db_session)
    target = create_user(db_session, username="target2", password="password123", role=UserRole.viewer, actor_user_id=owner.id)

    try:
        update_user(db_session, target.id, role=UserRole.group_admin, is_active=None, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 400

    db_session.refresh(target)
    assert target.role == UserRole.viewer


def test_update_user_allows_moving_a_group_admin_away_from_the_role(db_session):
    """The one direction that's blocked is *assigning* `group_admin` by
    hand — promoting an already-claimed `group_admin` to a full `admin` (or
    any other role) is a normal, allowed role change."""
    owner = _seed_owner(db_session)
    provisioned = _seed_unclaimed_group_admin(db_session)

    updated = update_user(db_session, provisioned.id, role=UserRole.admin, is_active=None, actor_user_id=owner.id)
    assert updated.role == UserRole.admin


# ---------------------------------------------------------------------------
# resend_claim_code
# ---------------------------------------------------------------------------


def test_resend_claim_code_sends_and_writes_audit_event(db_session):
    owner = _seed_owner(db_session)
    provisioned = _seed_unclaimed_group_admin(db_session, is_approved=True)
    provider = MockWhatsAppProvider()

    resend_claim_code(db_session, provider, provisioned.id, actor_user_id=owner.id)

    assert len(provider._sent_messages) == 1

    from communeer.models import AuditEvent

    events = db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "user.claim_code_resent", AuditEvent.target_id == str(provisioned.id))
    ).scalars().all()
    assert len(events) == 1


def test_resend_claim_code_rejects_an_already_claimed_account(db_session):
    owner = _seed_owner(db_session)
    target = create_user(db_session, username="target3", password="password123", role=UserRole.viewer, actor_user_id=owner.id)

    try:
        resend_claim_code(db_session, MockWhatsAppProvider(), target.id, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 400


def test_resend_claim_code_rejects_an_account_with_no_member_link(db_session):
    owner = _seed_owner(db_session)

    try:
        resend_claim_code(db_session, MockWhatsAppProvider(), owner.id, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 400


def test_resend_claim_code_rejects_an_unapproved_account(db_session):
    """An owner must use `approve_group_admin` for a never-yet-approved
    account — `resend_claim_code` is only for retrying after that."""
    owner = _seed_owner(db_session)
    provisioned = _seed_unclaimed_group_admin(db_session)  # is_approved=False by default

    try:
        resend_claim_code(db_session, MockWhatsAppProvider(), provisioned.id, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 400


def test_resend_claim_code_surfaces_a_503_on_provider_failure(db_session):
    owner = _seed_owner(db_session)
    provisioned = _seed_unclaimed_group_admin(db_session, is_approved=True)

    try:
        resend_claim_code(db_session, _FailingSendProvider(), provisioned.id, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 503


# ---------------------------------------------------------------------------
# approve_group_admin
# ---------------------------------------------------------------------------


def test_approve_group_admin_sends_code_and_writes_audit_event(db_session):
    owner = _seed_owner(db_session)
    provisioned = _seed_unclaimed_group_admin(db_session)  # is_approved=False by default
    provider = MockWhatsAppProvider()

    approve_group_admin(db_session, provider, provisioned.id, actor_user_id=owner.id)

    db_session.refresh(provisioned)
    assert provisioned.is_approved is True
    assert len(provider._sent_messages) == 1

    from communeer.models import AuditEvent

    events = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.action == "user.group_admin_approved", AuditEvent.target_id == str(provisioned.id)
        )
    ).scalars().all()
    assert len(events) == 1


def test_approve_group_admin_rejects_an_already_approved_account(db_session):
    owner = _seed_owner(db_session)
    provisioned = _seed_unclaimed_group_admin(db_session, is_approved=True)

    try:
        approve_group_admin(db_session, MockWhatsAppProvider(), provisioned.id, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 409


def test_approve_group_admin_rejects_an_already_claimed_account(db_session):
    owner = _seed_owner(db_session)
    target = create_user(db_session, username="target4", password="password123", role=UserRole.viewer, actor_user_id=owner.id)

    try:
        approve_group_admin(db_session, MockWhatsAppProvider(), target.id, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 400


def test_approve_group_admin_rejects_an_account_with_no_member_link(db_session):
    owner = _seed_owner(db_session)

    try:
        approve_group_admin(db_session, MockWhatsAppProvider(), owner.id, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 400


def test_approve_group_admin_persists_the_approval_even_if_the_send_fails(db_session):
    """A provider hiccup on the very first send must not force the owner to
    redo the approval decision — `is_approved` stays `True`, retryable via
    `resend_claim_code`."""
    owner = _seed_owner(db_session)
    provisioned = _seed_unclaimed_group_admin(db_session)  # is_approved=False by default

    try:
        approve_group_admin(db_session, _FailingSendProvider(), provisioned.id, actor_user_id=owner.id)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status_code == 503

    db_session.refresh(provisioned)
    assert provisioned.is_approved is True


# ---------------------------------------------------------------------------
# HTTP-level: owner-only gating
# ---------------------------------------------------------------------------




_PLAIN_ADMIN_TOTP_SECRET = "KRSXG5CTMVRXEZLU"


def _seed_admin_role_user() -> None:
    from communeer.auth.security import encrypt_totp_secret
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
                # 2FA is mandatory for `admin`/`owner` (see `deps.get_current_user`)
                # — pre-enabled here so this test exercises the *role* gate on
                # `/users`, not the separate "set up 2FA first" gate.
                totp_enabled=True,
                totp_secret_encrypted=encrypt_totp_secret(_PLAIN_ADMIN_TOTP_SECRET),
            )
        )
        db.commit()
    finally:
        db.close()


def test_users_route_requires_owner_role(client):
    import pyotp

    _seed_admin_role_user()
    login_response = client.post(
        "/api/v1/auth/login", json={"username": "plain-admin", "password": "plain-admin-pw-123"}
    )
    assert login_response.json()["requiresTotp"] is True
    code = pyotp.TOTP(_PLAIN_ADMIN_TOTP_SECRET).now()
    verify_response = client.post("/api/v1/auth/login/verify-totp", json={"code": code})
    assert verify_response.status_code == 200

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
