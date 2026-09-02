"""`auth/claim_service.py`: the WhatsApp-code claim flow an auto-provisioned
`group_admin` account (see `auth/provisioning.py`) uses to become usable.

Every account starts unapproved (`is_approved=False`) — nothing is ever sent
until an owner explicitly approves it (`users/service.py::
approve_group_admin`, exercised in `test_users.py`). These tests use `_approve`
below as a test-only shortcut to flip that flag directly (without going
through `approve_group_admin`'s own send), so `request_claim`/`complete_claim`'s
own send/verify mechanics can be exercised cleanly and independently.

See `test_group_admin_permission_boundaries.py` for the full HTTP-level
happy path (approve -> claim -> mandatory 2FA setup -> scoped access, over
the shared app database); this file exercises `request_claim`/`complete_claim`
directly against an isolated `db_session`, focusing on the edge cases:
the unapproved gate, wrong/expired code, lockout, oracle-safety, and
username collision.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from communeer.auth.claim_service import complete_claim, request_claim
from communeer.auth.security import PENDING_2FA_MAX_AGE_SECONDS, verify_password
from communeer.config import get_settings
from communeer.errors import ApiError
from communeer.models import (
    AuditEvent,
    Community,
    Group,
    GroupMembership,
    Member,
    MembershipStatus,
    User,
)
from communeer.providers.whatsapp.mock import MockWhatsAppProvider
from communeer.sync.service import sync_community

UNITY_WA_ID = "120363010000000001@g.us"
CLAIM_PASSWORD = "a-freshly-claimed-password"


def _sync_unity(db_session, provider: MockWhatsAppProvider) -> Community:
    return sync_community(db_session, provider, UNITY_WA_ID)


def _get_group(db_session, name: str) -> Group:
    return db_session.execute(select(Group).where(Group.name == name)).scalar_one()


def _get_unclaimed_admin(db_session, group: Group) -> tuple[Member, User]:
    row = db_session.execute(
        select(GroupMembership, Member)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(
            GroupMembership.group_id == group.id,
            GroupMembership.status == MembershipStatus.member,
            GroupMembership.is_admin.is_(True),
        )
    ).first()
    _membership, member = row
    user = db_session.execute(select(User).where(User.member_id == member.id)).scalar_one()
    assert user.is_claimed is False
    assert user.is_approved is False
    return member, user


def _approve(db_session, user: User) -> None:
    """Test-only shortcut for the `is_approved` half of what
    `approve_group_admin` (`test_users.py`) does — set directly rather than
    going through that function's own send, so `request_claim` here gets a
    genuinely fresh first-send opportunity of its own."""
    user.is_approved = True
    db_session.commit()


def _phone_for(member: Member) -> str:
    return f"+{member.wa_id.removesuffix('@c.us')}"


def _last_sent_code(provider: MockWhatsAppProvider, wa_id: str) -> str:
    for sent_wa_id, message in reversed(provider._sent_messages):
        if sent_wa_id == wa_id:
            match = re.search(r"\b(\d{6})\b", message)
            assert match is not None
            return match.group(1)
    raise AssertionError(f"no message was ever sent to {wa_id!r}")


def _expect_bad_request(fn) -> str:
    with pytest.raises(ApiError) as exc_info:
        fn()
    assert exc_info.value.status_code == 400
    return exc_info.value.message


# ---------------------------------------------------------------------------
# The unapproved gate: request_claim/complete_claim behave exactly like
# "unknown number" for an account no owner has approved yet
# ---------------------------------------------------------------------------


def test_request_claim_is_a_silent_no_op_for_an_unapproved_account(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, _user = _get_unclaimed_admin(db_session, general)

    # No `_approve` call here — still unapproved.
    request_claim(db_session, provider, _phone_for(member))
    assert provider._sent_messages == []


def test_complete_claim_rejects_an_unapproved_account_with_the_same_error_as_unknown(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, _user = _get_unclaimed_admin(db_session, general)
    phone = _phone_for(member)

    unapproved_message = _expect_bad_request(
        lambda: complete_claim(
            db_session, get_settings(), phone_number=phone, code="000000", username=None, password=CLAIM_PASSWORD
        )
    )
    unknown_message = _expect_bad_request(
        lambda: complete_claim(
            db_session, get_settings(), phone_number="+49 000 00000000", code="000000",
            username=None, password=CLAIM_PASSWORD,
        )
    )
    assert unapproved_message == unknown_message == "Invalid or expired code."


# ---------------------------------------------------------------------------
# request_claim: no-oracle no-op behavior (once approved)
# ---------------------------------------------------------------------------


def test_request_claim_sends_a_code_for_an_approved_phone(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, user = _get_unclaimed_admin(db_session, general)
    _approve(db_session, user)

    request_claim(db_session, provider, _phone_for(member))

    db_session.refresh(user)
    assert user.pending_otp_code_hash is not None
    assert user.pending_otp_sent_at is not None
    assert any(wa_id == member.wa_id for wa_id, _message in provider._sent_messages)


def test_request_claim_is_a_silent_no_op_for_an_unknown_phone(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)

    request_claim(db_session, provider, "+49 000 00000000")
    assert provider._sent_messages == []


def test_request_claim_is_a_silent_no_op_for_an_already_claimed_phone(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, user = _get_unclaimed_admin(db_session, general)
    _approve(db_session, user)
    phone = _phone_for(member)

    request_claim(db_session, provider, phone)
    code = _last_sent_code(provider, member.wa_id)
    complete_claim(db_session, get_settings(), phone_number=phone, code=code, username=None, password=CLAIM_PASSWORD)

    sent_before = len(provider._sent_messages)
    request_claim(db_session, provider, phone)
    assert len(provider._sent_messages) == sent_before


def test_request_claim_is_a_silent_no_op_when_locked_out(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, user = _get_unclaimed_admin(db_session, general)
    _approve(db_session, user)

    user.locked_until = datetime.now(UTC) + timedelta(minutes=5)
    db_session.commit()

    request_claim(db_session, provider, _phone_for(member))
    assert provider._sent_messages == []


# ---------------------------------------------------------------------------
# complete_claim: happy path
# ---------------------------------------------------------------------------


def test_complete_claim_with_correct_code_claims_the_account(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, user = _get_unclaimed_admin(db_session, general)
    _approve(db_session, user)
    phone = _phone_for(member)
    original_token_version = user.token_version

    request_claim(db_session, provider, phone)
    code = _last_sent_code(provider, member.wa_id)

    claimed = complete_claim(
        db_session, get_settings(), phone_number=phone, code=code, username=None, password=CLAIM_PASSWORD
    )

    assert claimed.id == user.id
    assert claimed.is_claimed is True
    assert claimed.claimed_at is not None
    assert claimed.token_version == original_token_version + 1
    assert claimed.username == user.username  # unchanged: no username override supplied
    assert verify_password(CLAIM_PASSWORD, claimed.password_hash)
    # The one-shot OTP challenge is consumed, not reusable.
    assert claimed.pending_otp_code_hash is None
    assert claimed.pending_otp_sent_at is None

    events = db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "auth.claimed", AuditEvent.target_id == str(user.id))
    ).scalars().all()
    assert len(events) == 1


def test_complete_claim_can_set_a_new_username(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, user = _get_unclaimed_admin(db_session, general)
    _approve(db_session, user)
    phone = _phone_for(member)

    request_claim(db_session, provider, phone)
    code = _last_sent_code(provider, member.wa_id)

    claimed = complete_claim(
        db_session,
        get_settings(),
        phone_number=phone,
        code=code,
        username="chosen-username",
        password=CLAIM_PASSWORD,
    )
    assert claimed.username == "chosen-username"


def test_complete_claim_rejects_a_username_already_taken(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    events = _get_group(db_session, "Events")
    member, user = _get_unclaimed_admin(db_session, general)
    _other_member, other_user = _get_unclaimed_admin(db_session, events)
    _approve(db_session, user)
    _approve(db_session, other_user)
    phone = _phone_for(member)

    request_claim(db_session, provider, phone)
    code = _last_sent_code(provider, member.wa_id)

    with pytest.raises(ApiError) as exc_info:
        complete_claim(
            db_session,
            get_settings(),
            phone_number=phone,
            code=code,
            username=other_user.username,
            password=CLAIM_PASSWORD,
        )
    assert exc_info.value.status_code == 409

    db_session.refresh(user)
    assert user.is_claimed is False  # the whole claim was rejected, not partially applied
    assert user.username != other_user.username


# ---------------------------------------------------------------------------
# complete_claim: wrong/expired code, lockout
# ---------------------------------------------------------------------------


def test_complete_claim_rejects_wrong_code_and_counts_it_as_a_failure(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, user = _get_unclaimed_admin(db_session, general)
    _approve(db_session, user)
    phone = _phone_for(member)

    request_claim(db_session, provider, phone)

    with pytest.raises(ApiError) as exc_info:
        complete_claim(
            db_session, get_settings(), phone_number=phone, code="000000", username=None, password=CLAIM_PASSWORD
        )
    assert exc_info.value.status_code == 400

    db_session.refresh(user)
    assert user.is_claimed is False
    assert user.failed_login_count == 1


def test_complete_claim_rejects_an_expired_code(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, user = _get_unclaimed_admin(db_session, general)
    _approve(db_session, user)
    phone = _phone_for(member)

    request_claim(db_session, provider, phone)
    code = _last_sent_code(provider, member.wa_id)

    db_session.refresh(user)
    user.pending_otp_sent_at = datetime.now(UTC) - timedelta(seconds=PENDING_2FA_MAX_AGE_SECONDS + 5)
    db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        complete_claim(
            db_session, get_settings(), phone_number=phone, code=code, username=None, password=CLAIM_PASSWORD
        )
    assert exc_info.value.status_code == 400

    db_session.refresh(user)
    assert user.is_claimed is False


def test_complete_claim_locks_out_after_max_failed_attempts(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, user = _get_unclaimed_admin(db_session, general)
    _approve(db_session, user)
    phone = _phone_for(member)
    settings = get_settings()

    request_claim(db_session, provider, phone)
    correct_code = _last_sent_code(provider, member.wa_id)

    for _ in range(settings.login_max_failed_attempts):
        with pytest.raises(ApiError) as exc_info:
            complete_claim(
                db_session, settings, phone_number=phone, code="000000", username=None, password=CLAIM_PASSWORD
            )
        assert exc_info.value.status_code == 400

    db_session.refresh(user)
    assert user.locked_until is not None

    # Locked out now — even the *correct* code is rejected, with 429 (not
    # 400), before the code is ever checked.
    with pytest.raises(ApiError) as exc_info:
        complete_claim(
            db_session, settings, phone_number=phone, code=correct_code, username=None, password=CLAIM_PASSWORD
        )
    assert exc_info.value.status_code == 429

    db_session.refresh(user)
    assert user.is_claimed is False


# ---------------------------------------------------------------------------
# Oracle-safety: unknown phone, wrong code, and an already-claimed phone all
# look identical to `complete_claim`'s caller
# ---------------------------------------------------------------------------


def test_complete_claim_gives_identical_errors_for_unknown_wrong_code_and_already_claimed(db_session):
    provider = MockWhatsAppProvider()
    _sync_unity(db_session, provider)
    general = _get_group(db_session, "General")
    member, user = _get_unclaimed_admin(db_session, general)
    _approve(db_session, user)
    phone = _phone_for(member)

    request_claim(db_session, provider, phone)

    unknown_phone_message = _expect_bad_request(
        lambda: complete_claim(
            db_session, get_settings(), phone_number="+49 000 00000000", code="000000",
            username=None, password=CLAIM_PASSWORD,
        )
    )
    wrong_code_message = _expect_bad_request(
        lambda: complete_claim(
            db_session, get_settings(), phone_number=phone, code="000000",
            username=None, password=CLAIM_PASSWORD,
        )
    )

    code = _last_sent_code(provider, member.wa_id)
    complete_claim(db_session, get_settings(), phone_number=phone, code=code, username=None, password=CLAIM_PASSWORD)

    already_claimed_message = _expect_bad_request(
        lambda: complete_claim(
            db_session, get_settings(), phone_number=phone, code="000000",
            username=None, password=CLAIM_PASSWORD,
        )
    )

    assert unknown_phone_message == wrong_code_message == already_claimed_message == "Invalid or expired code."
