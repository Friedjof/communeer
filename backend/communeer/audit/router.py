from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from communeer.audit.schemas import AuditEventOut
from communeer.audit.service import list_audit_events
from communeer.deps import get_current_user, get_db

router = APIRouter(tags=["audit"], dependencies=[Depends(get_current_user)])


@router.get("/audit", response_model=list[AuditEventOut])
def list_audit(db: Session = Depends(get_db)) -> list[AuditEventOut]:
    return list_audit_events(db)
