import { useQuery } from '@tanstack/react-query'
import * as membersApi from './api'

// Reads Communeer's own local DB only (never WhatsApp/WPPConnect directly) —
// short polling here keeps the member list reflecting webhook-driven
// backend changes (see `communeer/webhooks/router.py`) without a manual
// "Sync now" click.
const LIVE_REFETCH_INTERVAL_MS = 25_000

export const memberKeys = {
  communityMembers: (communityId: string) => ['communities', communityId, 'members'] as const,
  detail: (memberId: string) => ['members', memberId] as const,
}

export function useCommunityMembers(communityId: string) {
  return useQuery({
    queryKey: memberKeys.communityMembers(communityId),
    queryFn: () => membersApi.getCommunityMembers(communityId),
    enabled: Boolean(communityId),
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}

export function useMember(memberId: string | null) {
  return useQuery({
    queryKey: memberKeys.detail(memberId ?? ''),
    queryFn: () => membersApi.getMember(memberId as string),
    enabled: Boolean(memberId),
  })
}
