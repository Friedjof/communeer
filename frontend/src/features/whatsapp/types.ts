import type { CommunitySummary } from '@/features/communities/types'

export type WhatsAppConnectionState = 'disconnected' | 'qr_pending' | 'connecting' | 'connected' | 'error'

export interface WhatsAppStatus {
  state: WhatsAppConnectionState
  qrCodeDataUrl: string | null
  detail: string | null
  /** Whether `POST /whatsapp/discover-and-sync` is currently running on the
   * server — lets the UI keep showing "Discovering…" across a page reload. */
  discoveryInProgress: boolean
}

/** A community the provider found but whose sync itself failed partway
 * through — surfaced here instead of only a backend log line. */
export interface DiscoverAndSyncFailure {
  waId: string
  name: string
  reason: string
}

/** Every community `POST /whatsapp/discover-and-sync` actually found and
 * synced — deliberately unfiltered, unlike `GET /communities`.
 * `hiddenNonAdminWaIds` is the subset that `GET /communities` will go on to
 * hide because the connected WhatsApp number isn't an admin there. */
export interface DiscoverAndSyncResult {
  communities: CommunitySummary[]
  hiddenNonAdminWaIds: string[]
  failed: DiscoverAndSyncFailure[]
}
