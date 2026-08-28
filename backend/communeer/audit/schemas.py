import uuid
from datetime import datetime

from communeer.schemas import CamelModel


class AuditEventOut(CamelModel):
    id: uuid.UUID
    actor_username: str | None
    action: str
    target_type: str | None
    target_id: str | None
    detail: dict | None
    occurred_at: datetime
