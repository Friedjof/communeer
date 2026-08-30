import { apiGet } from '@/api/client'
import type { GroupDetail, GroupJoinRequest, GroupMemberRow } from './types'

export function getGroup(groupId: string, advanced = false): Promise<GroupDetail> {
  const query = advanced ? '?advanced=true' : ''
  return apiGet<GroupDetail>(`/groups/${groupId}${query}`)
}

export function getGroupMembers(groupId: string): Promise<GroupMemberRow[]> {
  return apiGet<GroupMemberRow[]>(`/groups/${groupId}/members`)
}

export function getGroupRequests(groupId: string): Promise<GroupJoinRequest[]> {
  return apiGet<GroupJoinRequest[]>(`/groups/${groupId}/requests`)
}

export function getGroupInviteLink(groupId: string): Promise<{ inviteLink: string | null }> {
  return apiGet<{ inviteLink: string | null }>(`/groups/${groupId}/invite-link`)
}
