import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as moderationApi from './api'
import type { ModerationSection } from './types'

// Reads Communeer's own local DB only (never WhatsApp/WPPConnect directly) —
// short polling keeps the queue reflecting webhook-driven backend changes
// without a manual "Sync now" click, same convention as communities/members.
const LIVE_REFETCH_INTERVAL_MS = 25_000

export const moderationKeys = {
  queue: (communityId: string) => ['communities', communityId, 'moderation', 'queue'] as const,
}

export function useModerationQueue(communityId: string) {
  return useQuery({
    queryKey: moderationKeys.queue(communityId),
    queryFn: () => moderationApi.getModerationQueue(communityId),
    enabled: Boolean(communityId),
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}

interface DismissModerationItemInput {
  section: ModerationSection
  targetId: string
  reason?: string
}

export function useDismissModerationItem(communityId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ section, targetId, reason }: DismissModerationItemInput) =>
      moderationApi.dismissModerationItem(communityId, section, targetId, reason),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: moderationKeys.queue(communityId) })
    },
  })
}
