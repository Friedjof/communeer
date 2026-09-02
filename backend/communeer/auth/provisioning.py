"""Auto-provisioning of `group_admin` dashboard accounts for real WhatsApp
group admins.

Idempotent get-or-create keyed on `User.member_id` (mirrors
`sync/service.py::_upsert_member`'s natural-key upsert shape), called from
BOTH places `GroupMembership.is_admin` can be written — `sync/service.py`
(covers "Sync now"/"Discover and sync"/the boot-time priming loop/the
webhook-triggered resync, i.e. promotions done directly in WhatsApp) and
`groups/service.py::set_group_member_admin` (the manual dashboard promote
button, which never goes through `sync_community`) — see each call site for
why reconciliation, not edge-triggering, is the right model here.

**Never sends a WhatsApp message on its own.** Discovering/syncing a real
admin only ever creates an unclaimed, unapproved account — no message goes
out until an owner explicitly approves it (`users/service.py::
approve_group_admin`), the one and only place `send_claim_code` is called
outside of the person's own self-service `/auth/claim/request`. This is a
deliberate product decision (see AGENTS.md's "never let Communeer write to
WhatsApp automatically" principle, and the incident that prompted tightening
this beyond that): a background sync must never be the thing that decides a
real person gets messaged.
"""

import logging
import re
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from communeer.auth.security import hash_password
from communeer.auth.service import _send_pending_otp
from communeer.models import AuditEvent, Group, GroupMembership, Member, User, UserRole
from communeer.providers.whatsapp.base import WhatsAppProvider

logger = logging.getLogger("communeer.auth.provisioning")


def _slugify_username(display_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
    return slug or "member"


def _generate_unique_username(db: Session, base: str) -> str:
    candidate = _slugify_username(base)[:64]
    n = 2
    while db.execute(select(User.id).where(User.username == candidate)).scalar_one_or_none() is not None:
        suffix = f"-{n}"
        candidate = f"{_slugify_username(base)[: 64 - len(suffix)]}{suffix}"
        n += 1
    return candidate


def ensure_group_admin_account(db: Session, member: Member) -> tuple[User, bool]:
    """Get-or-create a `group_admin` `User` linked to `member`. Returns
    `(user, created)` — `created` is only `True` the first time. Never
    touches `role`/`password_hash`/`is_claimed`/`is_approved`/`username` on
    an already-linked user, so calling this repeatedly (every sync, for
    every currently-admin membership) is safe and doesn't disturb an
    in-progress or already-completed claim (or a pending approval
    decision)."""
    existing = db.execute(select(User).where(User.member_id == member.id)).scalar_one_or_none()
    if existing is not None:
        return existing, False

    username = _generate_unique_username(db, member.display_name)
    user = User(
        username=username,
        # A random, never-communicated placeholder — nobody needs to know
        # it, since `authenticate_password` already refuses to log in an
        # unclaimed account regardless (see that function's docstring).
        # `complete_claim` overwrites this with the claimant's real chosen
        # password.
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=UserRole.group_admin,
        is_active=True,
        is_claimed=False,
        # Requires an explicit owner decision (`approve_group_admin`) before
        # any message ever goes out — see this module's docstring.
        is_approved=False,
        member_id=member.id,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.execute(select(User).where(User.member_id == member.id)).scalar_one_or_none()
        if existing is not None:
            return existing, False  # lost a race to a concurrent provisioning call
        raise

    db.add(
        AuditEvent(
            actor_user_id=None,
            action="user.auto_provisioned",
            target_type="user",
            target_id=str(user.id),
            detail={"memberId": str(member.id), "username": username},
        )
    )
    db.commit()
    db.refresh(user)
    return user, True


def send_claim_code(db: Session, provider: WhatsAppProvider, user: User) -> None:
    """A claim code is structurally identical to a WhatsApp-OTP code — reuse
    `auth/service.py`'s send primitive verbatim, including its resend
    cooldown and the shared `pending_otp_code_hash`/`pending_otp_sent_at`
    slot. Safe to share that slot: an unclaimed user has
    `whatsapp_otp_enabled=False` and no reachable login path (see
    `authenticate_password`), so nothing else can be mid-flight on it."""
    member = db.get(Member, user.member_id)
    _send_pending_otp(db, provider, user, member.wa_id)


def reconcile_admin_provisioning_for_group(db: Session, group_id: uuid.UUID) -> None:
    """Ensures every CURRENTLY-admin `GroupMembership` for `group_id` has a
    linked `User`, auto-provisioning any that don't (unclaimed, unapproved —
    see this module's docstring for why no message is ever sent here).
    Deliberately a full reconciliation pass, not an edge-triggered "only on
    False->True" check — `is_admin`'s prior value isn't captured anywhere in
    the two write paths today, and reconciling is what makes provisioning
    also catch admins that already existed before this feature shipped.
    Each check is one cheap indexed lookup (`ensure_group_admin_account`'s
    `member_id` query), so running it on every sync for every group is not
    a meaningful cost."""
    members = db.execute(
        select(Member)
        .join(GroupMembership, GroupMembership.member_id == Member.id)
        .where(GroupMembership.group_id == group_id, GroupMembership.is_admin.is_(True))
    ).scalars().all()
    for member in members:
        ensure_group_admin_account(db, member)


def reconcile_admin_provisioning_for_community(db: Session, community_id: uuid.UUID) -> None:
    group_ids = db.execute(select(Group.id).where(Group.community_id == community_id)).scalars().all()
    for group_id in group_ids:
        reconcile_admin_provisioning_for_group(db, group_id)
