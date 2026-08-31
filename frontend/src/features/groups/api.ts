import { apiGet, apiPost } from '@/api/client'
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

export function approveJoinRequest(groupId: string, memberId: string): Promise<void> {
  return apiPost<void>(`/groups/${groupId}/requests/${memberId}/approve`)
}

export function rejectJoinRequest(groupId: string, memberId: string): Promise<void> {
  return apiPost<void>(`/groups/${groupId}/requests/${memberId}/reject`)
}

export function removeGroupMember(groupId: string, memberId: string): Promise<void> {
  return apiPost<void>(`/groups/${groupId}/members/${memberId}/remove`)
}

export function promoteGroupMember(groupId: string, memberId: string): Promise<void> {
  return apiPost<void>(`/groups/${groupId}/members/${memberId}/promote`)
}

export function demoteGroupMember(groupId: string, memberId: string): Promise<void> {
  return apiPost<void>(`/groups/${groupId}/members/${memberId}/demote`)
}
