import { apiGet, apiPost } from '@/api/client'
import type { GroupDetail, GroupJoinRequest, GroupMemberRow, GroupMessage } from './types'

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

export interface GetGroupMessagesParams {
  limit?: number
  before?: string
  search?: string
  memberId?: string
}

export function getGroupMessages(groupId: string, params: GetGroupMessagesParams = {}): Promise<GroupMessage[]> {
  const query = new URLSearchParams()
  if (params.limit !== undefined) query.set('limit', String(params.limit))
  if (params.before) query.set('before', params.before)
  if (params.search) query.set('search', params.search)
  if (params.memberId) query.set('member_id', params.memberId)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return apiGet<GroupMessage[]>(`/groups/${groupId}/messages${suffix}`)
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
