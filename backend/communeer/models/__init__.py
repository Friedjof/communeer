"""SQLAlchemy models. Import this module to register all mapped classes on
`Base.metadata` (needed by Alembic autogenerate and by `Base.metadata.create_all`
in tests).
"""

from communeer.models.audit import AuditEvent
from communeer.models.base import Base
from communeer.models.community import Community
from communeer.models.group import Group
from communeer.models.member import Member
from communeer.models.membership import ActivityType, GroupMembership, MembershipStatus
from communeer.models.message import GroupMessage, MessageType
from communeer.models.moderation import ModerationDismissal
from communeer.models.renewal import (
    RenewalCampaign,
    RenewalConfirmation,
    RenewalConfirmationStatus,
)
from communeer.models.snapshot import CommunityMemberSnapshot, GroupMemberSnapshot
from communeer.models.user import User, UserRecoveryCode, UserRole

__all__ = [
    "ActivityType",
    "AuditEvent",
    "Base",
    "Community",
    "CommunityMemberSnapshot",
    "Group",
    "GroupMemberSnapshot",
    "GroupMembership",
    "GroupMessage",
    "Member",
    "MembershipStatus",
    "MessageType",
    "ModerationDismissal",
    "RenewalCampaign",
    "RenewalConfirmation",
    "RenewalConfirmationStatus",
    "User",
    "UserRecoveryCode",
    "UserRole",
]
