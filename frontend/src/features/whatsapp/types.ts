export type WhatsAppConnectionState = 'disconnected' | 'qr_pending' | 'connecting' | 'connected' | 'error'

export interface WhatsAppStatus {
  state: WhatsAppConnectionState
  qrCodeDataUrl: string | null
  detail: string | null
  /** Whether `POST /whatsapp/discover-and-sync` is currently running on the
   * server — lets the UI keep showing "Discovering…" across a page reload. */
  discoveryInProgress: boolean
}
