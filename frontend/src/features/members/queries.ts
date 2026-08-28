import { useQuery } from '@tanstack/react-query'
import * as membersApi from './api'

export const memberKeys = {
  communityMembers: (communityId: string) => ['communities', communityId, 'members'] as const,
  detail: (memberId: string) => ['members', memberId] as const,
}

export function useCommunityMembers(communityId: string) {
  return useQuery({
    queryKey: memberKeys.communityMembers(communityId),
    queryFn: () => membersApi.getCommunityMembers(communityId),
    enabled: Boolean(communityId),
  })
}

export function useMember(memberId: string | null) {
  return useQuery({
    queryKey: memberKeys.detail(memberId ?? ''),
    queryFn: () => membersApi.getMember(memberId as string),
    enabled: Boolean(memberId),
  })
}
