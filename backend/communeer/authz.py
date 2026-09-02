"""Per-`group_admin` group/community access scoping.

`owner`/`admin`/`viewer` are unaffected by anything in this module — their
access stays exactly as global as it always was. Only `UserRole.group_admin`
(see `models/user.py`) is additionally constrained here, to precisely the
group(s) their linked `Member` currently administers in WhatsApp.

Deliberately **not** a stored permissions table: every function below derives
its answer live from `GroupMembership.is_admin` rows, the same "derive,
don't duplicate" philosophy already established elsewhere in this codebase
(see `models/membership.py`'s docstring on why `CommunityMembership` isn't a
stored table either) — there is exactly one source of truth for "who
administers what" (the synced WhatsApp state), so a `group_admin`'s access
can never drift out of sync with reality the way a separately-maintained
permissions table could.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.errors import forbidden
from communeer.models import Group, GroupMembership, User, UserRole

# Roles whose access this module never narrows — global by design, unchanged
# by this feature.
_UNRESTRICTED_ROLES = (UserRole.owner, UserRole.admin, UserRole.viewer)


def get_administered_group_ids(db: Session, user: User) -> set[uuid.UUID]:
    """Every `group_id` this user's linked `Member` is currently
    `GroupMembership.is_admin=True` for. Empty for `member_id is None`
    (never claimed / not a `group_admin` at all) or a member who currently
    administers nothing anywhere (demoted/removed from every group they
    used to administer) — no explicit deactivation is needed elsewhere in
    the codebase for that case, since every check below naturally reflects
    it on the next call."""
    if user.member_id is None:
        return set()
    return set(
        db.execute(
            select(GroupMembership.group_id).where(
                GroupMembership.member_id == user.member_id,
                GroupMembership.is_admin.is_(True),
            )
        ).scalars()
    )


def get_administered_community_ids(db: Session, user: User) -> set[uuid.UUID]:
    group_ids = get_administered_group_ids(db, user)
    if not group_ids:
        return set()
    return set(db.execute(select(Group.community_id).where(Group.id.in_(group_ids))).scalars())


def ensure_group_access(db: Session, user: User, group_id: uuid.UUID) -> None:
    """Composes with, never replaces, `require_role`: that answers "may this
    role call this route at all," this answers "which `group_id`." Owner/
    admin/viewer pass through unconditionally."""
    if user.role in _UNRESTRICTED_ROLES:
        return
    if user.role is UserRole.group_admin and group_id in get_administered_group_ids(db, user):
        return
    raise forbidden("You do not have access to this group.")


def ensure_community_access(db: Session, user: User, community_id: uuid.UUID) -> None:
    if user.role in _UNRESTRICTED_ROLES:
        return
    if user.role is UserRole.group_admin and community_id in get_administered_community_ids(db, user):
        return
    raise forbidden("You do not have access to this community.")
