import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { memberKeys } from '../members/queries'
import * as communitiesApi from './api'

export const communityKeys = {
  all: ['communities'] as const,
  detail: (communityId: string) => ['communities', communityId] as const,
  groups: (communityId: string) => ['communities', communityId, 'groups'] as const,
  history: (communityId: string) => ['communities', communityId, 'history'] as const,
  groupsHistory: (communityId: string) => ['communities', communityId, 'groups', 'history'] as const,
}

export function communitiesQueryOptions() {
  return queryOptions({
    queryKey: communityKeys.all,
    queryFn: communitiesApi.getCommunities,
  })
}

export function useCommunities() {
  return useQuery(communitiesQueryOptions())
}

export function useCommunity(communityId: string) {
  return useQuery({
    queryKey: communityKeys.detail(communityId),
    queryFn: () => communitiesApi.getCommunity(communityId),
    enabled: Boolean(communityId),
  })
}

export function useCommunityGroups(communityId: string) {
  return useQuery({
    queryKey: communityKeys.groups(communityId),
    queryFn: () => communitiesApi.getCommunityGroups(communityId),
    enabled: Boolean(communityId),
  })
}

export function useCommunityHistory(communityId: string) {
  return useQuery({
    queryKey: communityKeys.history(communityId),
    queryFn: () => communitiesApi.getCommunityHistory(communityId),
    enabled: Boolean(communityId),
  })
}

export function useCommunityGroupsHistory(communityId: string) {
  return useQuery({
    queryKey: communityKeys.groupsHistory(communityId),
    queryFn: () => communitiesApi.getCommunityGroupsHistory(communityId),
    enabled: Boolean(communityId),
  })
}

export function useSyncCommunity(communityId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => communitiesApi.syncCommunity(communityId),
    onSuccess: (community) => {
      queryClient.setQueryData(communityKeys.detail(communityId), community)
      void queryClient.invalidateQueries({ queryKey: communityKeys.all })
      void queryClient.invalidateQueries({ queryKey: communityKeys.groups(communityId) })
      void queryClient.invalidateQueries({ queryKey: communityKeys.history(communityId) })
      void queryClient.invalidateQueries({ queryKey: communityKeys.groupsHistory(communityId) })
      void queryClient.invalidateQueries({ queryKey: memberKeys.communityMembers(communityId) })
    },
  })
}
