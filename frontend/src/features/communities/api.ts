import { apiGet, apiPost } from '@/api/client'
import type { GroupSummary } from '../groups/types'
import type { CommunityDetail, CommunityHistoryPoint, CommunitySummary, GroupHistorySeries } from './types'

export function getCommunities(): Promise<CommunitySummary[]> {
  return apiGet<CommunitySummary[]>('/communities')
}

export function getCommunity(communityId: string, advanced = false): Promise<CommunityDetail> {
  const query = advanced ? '?advanced=true' : ''
  return apiGet<CommunityDetail>(`/communities/${communityId}${query}`)
}

export function getCommunityGroups(communityId: string): Promise<GroupSummary[]> {
  return apiGet<GroupSummary[]>(`/communities/${communityId}/groups`)
}

export function syncCommunity(communityId: string): Promise<CommunityDetail> {
  return apiPost<CommunityDetail>(`/communities/${communityId}/sync`)
}

export function getCommunityHistory(communityId: string): Promise<CommunityHistoryPoint[]> {
  return apiGet<CommunityHistoryPoint[]>(`/communities/${communityId}/history`)
}

export function getCommunityGroupsHistory(communityId: string): Promise<GroupHistorySeries[]> {
  return apiGet<GroupHistorySeries[]>(`/communities/${communityId}/groups/history`)
}
