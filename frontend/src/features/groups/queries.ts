import { queryOptions, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as groupsApi from './api'

const GROUP_MESSAGES_PAGE_SIZE = 50

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
  messages: (groupId: string, filters: { search?: string; memberId?: string }) =>
    ['groups', groupId, 'messages', filters] as const,
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

/** A group's message log, paginated backwards from "now" via the `before`
 * cursor (the oldest already-loaded message's `sentAt`) — never offset-based,
 * since an offset would shift under the caller as new messages keep
 * arriving on this live-appending table. No live polling: a log a human is
 * scrolling through doesn't need the 25s badge-refresh cadence the rest of
 * this file uses. */
export function useGroupMessages(groupId: string, filters: { search?: string; memberId?: string }) {
  return useInfiniteQuery({
    queryKey: groupKeys.messages(groupId, filters),
    queryFn: ({ pageParam }: { pageParam?: string }) =>
      groupsApi.getGroupMessages(groupId, { ...filters, limit: GROUP_MESSAGES_PAGE_SIZE, before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.length === GROUP_MESSAGES_PAGE_SIZE ? lastPage.at(-1)?.sentAt : undefined,
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

/** Shared invalidation after any membership-mutating action (approve/reject/
 * remove/promote/demote): the requests list, member list, and pending/admin
 * counts embedded in the group detail can all change together. */
function useInvalidateGroupMembership(groupId: string) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: groupKeys.requests(groupId) })
    void queryClient.invalidateQueries({ queryKey: groupKeys.members(groupId) })
    void queryClient.invalidateQueries({ queryKey: ['groups', groupId], exact: false })
  }
}

export function useApproveJoinRequest(groupId: string) {
  const invalidate = useInvalidateGroupMembership(groupId)
  return useMutation({
    mutationFn: (memberId: string) => groupsApi.approveJoinRequest(groupId, memberId),
    onSuccess: invalidate,
  })
}

export function useRejectJoinRequest(groupId: string) {
  const invalidate = useInvalidateGroupMembership(groupId)
  return useMutation({
    mutationFn: (memberId: string) => groupsApi.rejectJoinRequest(groupId, memberId),
    onSuccess: invalidate,
  })
}

export function useRemoveGroupMember(groupId: string) {
  const invalidate = useInvalidateGroupMembership(groupId)
  return useMutation({
    mutationFn: (memberId: string) => groupsApi.removeGroupMember(groupId, memberId),
    onSuccess: invalidate,
  })
}

export function usePromoteGroupMember(groupId: string) {
  const invalidate = useInvalidateGroupMembership(groupId)
  return useMutation({
    mutationFn: (memberId: string) => groupsApi.promoteGroupMember(groupId, memberId),
    onSuccess: invalidate,
  })
}

export function useDemoteGroupMember(groupId: string) {
  const invalidate = useInvalidateGroupMembership(groupId)
  return useMutation({
    mutationFn: (memberId: string) => groupsApi.demoteGroupMember(groupId, memberId),
    onSuccess: invalidate,
  })
}
