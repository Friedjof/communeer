from communeer.providers.whatsapp.base import WhatsAppConnectionState
from communeer.schemas import CamelModel


class WhatsAppStatusOut(CamelModel):
    state: WhatsAppConnectionState
    qr_code_data_url: str | None
    detail: str | None
