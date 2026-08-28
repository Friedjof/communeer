"""SQLAlchemy models. Import this module to register all mapped classes on
`Base.metadata` (needed by Alembic autogenerate and by `Base.metadata.create_all`
in tests).
"""

from communeer.models.audit import AuditEvent
from communeer.models.base import Base
from communeer.models.community import Community
from communeer.models.group import Group
from communeer.models.member import Member
from communeer.models.membership import GroupMembership, MembershipStatus
from communeer.models.renewal import (
    RenewalCampaign,
    RenewalConfirmation,
    RenewalConfirmationStatus,
)
from communeer.models.snapshot import CommunityMemberSnapshot, GroupMemberSnapshot
from communeer.models.user import User, UserRole

__all__ = [
    "AuditEvent",
    "Base",
    "Community",
    "CommunityMemberSnapshot",
    "Group",
    "GroupMemberSnapshot",
    "GroupMembership",
    "Member",
    "MembershipStatus",
    "RenewalCampaign",
    "RenewalConfirmation",
    "RenewalConfirmationStatus",
    "User",
    "UserRole",
]
