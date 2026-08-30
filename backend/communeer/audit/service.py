from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.audit.schemas import AuditEventOut
from communeer.models import AuditEvent, User


def list_audit_events(
    db: Session,
    limit: int = 500,
    action: str | None = None,
    target_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[AuditEventOut]:
    query = select(AuditEvent, User).outerjoin(User, User.id == AuditEvent.actor_user_id)

    if action:
        query = query.where(AuditEvent.action == action)
    if target_type:
        query = query.where(AuditEvent.target_type == target_type)
    if since:
        query = query.where(AuditEvent.occurred_at >= since)
    if until:
        query = query.where(AuditEvent.occurred_at <= until)

    rows = db.execute(query.order_by(AuditEvent.occurred_at.desc()).limit(limit)).all()
    return [
        AuditEventOut(
            id=event.id,
            actor_username=user.username if user else None,
            action=event.action,
            target_type=event.target_type,
            target_id=event.target_id,
            detail=event.detail,
            occurred_at=event.occurred_at,
        )
        for event, user in rows
    ]
