import { apiGet, apiPost } from '@/api/client'
import type { DiscoverAndSyncResult, WhatsAppStatus } from './types'

export function getWhatsAppStatus(): Promise<WhatsAppStatus> {
  return apiGet<WhatsAppStatus>('/whatsapp/status')
}

export function connectWhatsApp(): Promise<void> {
  return apiPost<void>('/whatsapp/connect')
}

export function discoverAndSyncCommunities(): Promise<DiscoverAndSyncResult> {
  return apiPost<DiscoverAndSyncResult>('/whatsapp/discover-and-sync')
}
