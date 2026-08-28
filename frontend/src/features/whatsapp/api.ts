import { apiGet, apiPost } from '@/api/client'
import type { CommunitySummary } from '@/features/communities/types'
import type { WhatsAppStatus } from './types'

export function getWhatsAppStatus(): Promise<WhatsAppStatus> {
  return apiGet<WhatsAppStatus>('/whatsapp/status')
}

export function connectWhatsApp(): Promise<void> {
  return apiPost<void>('/whatsapp/connect')
}

export function discoverAndSyncCommunities(): Promise<CommunitySummary[]> {
  return apiPost<CommunitySummary[]>('/whatsapp/discover-and-sync')
}
