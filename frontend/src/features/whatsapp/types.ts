export type WhatsAppConnectionState = 'disconnected' | 'qr_pending' | 'connecting' | 'connected' | 'error'

export interface WhatsAppStatus {
  state: WhatsAppConnectionState
  qrCodeDataUrl: string | null
  detail: string | null
}
