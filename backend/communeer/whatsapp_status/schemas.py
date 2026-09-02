from communeer.providers.whatsapp.base import WhatsAppConnectionState
from communeer.schemas import CamelModel


class WhatsAppStatusOut(CamelModel):
    state: WhatsAppConnectionState
    qr_code_data_url: str | None
    detail: str | None
    # Whether `POST /whatsapp/discover-and-sync` is currently running (see
    # `whatsapp_status/router.py`'s module-level lock) — lets the frontend
    # keep showing "Discovering…" across a page reload, since that endpoint
    # is a single long-running synchronous request with no other persisted
    # progress signal.
    discovery_in_progress: bool
