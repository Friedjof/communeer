from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from communeer.audit.schemas import AuditEventOut
from communeer.audit.service import list_audit_events
from communeer.deps import get_db, require_role
from communeer.models import UserRole

# Owner/admin only, not viewer — the audit log can reveal who did what
# (including other users' logins/actions), which a viewer role isn't meant
# to see.
router = APIRouter(tags=["audit"], dependencies=[Depends(require_role(UserRole.owner, UserRole.admin))])


@router.get("/audit", response_model=list[AuditEventOut])
def list_audit(
    db: Session = Depends(get_db),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None, alias="targetType"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> list[AuditEventOut]:
    return list_audit_events(db, action=action, target_type=target_type, since=since, until=until)
