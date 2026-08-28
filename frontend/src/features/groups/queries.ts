import { queryOptions, useQuery } from '@tanstack/react-query'
import * as groupsApi from './api'

export const groupKeys = {
  all: ['groups'] as const,
  detail: (groupId: string, advanced: boolean) => ['groups', groupId, { advanced }] as const,
  members: (groupId: string) => ['groups', groupId, 'members'] as const,
  requests: (groupId: string) => ['groups', groupId, 'requests'] as const,
}

export function groupQueryOptions(groupId: string, advanced = false) {
  return queryOptions({
    queryKey: groupKeys.detail(groupId, advanced),
    queryFn: () => groupsApi.getGroup(groupId, advanced),
    enabled: Boolean(groupId),
  })
}

export function useGroup(groupId: string, advanced = false) {
  return useQuery(groupQueryOptions(groupId, advanced))
}

export function useGroupMembers(groupId: string) {
  return useQuery({
    queryKey: groupKeys.members(groupId),
    queryFn: () => groupsApi.getGroupMembers(groupId),
    enabled: Boolean(groupId),
  })
}

export function useGroupRequests(groupId: string) {
  return useQuery({
    queryKey: groupKeys.requests(groupId),
    queryFn: () => groupsApi.getGroupRequests(groupId),
    enabled: Boolean(groupId),
  })
}
