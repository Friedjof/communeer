import { apiGet } from '@/api/client'
import type { CommunityMemberRow, MemberDetail } from './types'

export function getCommunityMembers(communityId: string): Promise<CommunityMemberRow[]> {
  return apiGet<CommunityMemberRow[]>(`/communities/${communityId}/members`)
}

export function getMember(memberId: string): Promise<MemberDetail> {
  return apiGet<MemberDetail>(`/members/${memberId}`)
}
