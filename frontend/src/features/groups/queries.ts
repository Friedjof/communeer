import { queryOptions, useQuery } from '@tanstack/react-query'
import * as groupsApi from './api'

// Reads Communeer's own local DB only (never WhatsApp/WPPConnect directly) —
// short polling here keeps the group member list reflecting webhook-driven
// backend changes (see `communeer/webhooks/router.py`) without a manual
// "Sync now" click.
const LIVE_REFETCH_INTERVAL_MS = 25_000

export const groupKeys = {
  all: ['groups'] as const,
  detail: (groupId: string, advanced: boolean) => ['groups', groupId, { advanced }] as const,
  members: (groupId: string) => ['groups', groupId, 'members'] as const,
  requests: (groupId: string) => ['groups', groupId, 'requests'] as const,
  inviteLink: (groupId: string) => ['groups', groupId, 'invite-link'] as const,
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
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}

export function useGroupRequests(groupId: string) {
  return useQuery({
    queryKey: groupKeys.requests(groupId),
    queryFn: () => groupsApi.getGroupRequests(groupId),
    enabled: Boolean(groupId),
  })
}

/** Fetched only on demand (`enabled: false` — call `refetch()` from a
 * button click), never prefetched alongside the rest of a group's data —
 * a separate WPPConnect call nobody asked for on every page load would
 * violate this codebase's cost posture. */
export function useGroupInviteLink(groupId: string) {
  return useQuery({
    queryKey: groupKeys.inviteLink(groupId),
    queryFn: () => groupsApi.getGroupInviteLink(groupId),
    enabled: false,
    staleTime: 60_000,
    retry: false,
  })
}
