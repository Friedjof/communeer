import { apiGet, apiPost } from '@/api/client'
import type { ModerationQueue, ModerationSection } from './types'

export function getModerationQueue(communityId: string): Promise<ModerationQueue> {
  return apiGet<ModerationQueue>(`/communities/${communityId}/moderation/queue`)
}

export function dismissModerationItem(
  communityId: string,
  section: ModerationSection,
  targetId: string,
  reason?: string,
): Promise<void> {
  return apiPost<void>(`/communities/${communityId}/moderation/dismissals`, {
    section,
    targetId,
    reason,
  })
}
