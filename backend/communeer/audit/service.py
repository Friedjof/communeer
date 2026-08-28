from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.audit.schemas import AuditEventOut
from communeer.models import AuditEvent, User


def list_audit_events(db: Session, limit: int = 500) -> list[AuditEventOut]:
    rows = db.execute(
        select(AuditEvent, User)
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .order_by(AuditEvent.occurred_at.desc())
        .limit(limit)
    ).all()
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
