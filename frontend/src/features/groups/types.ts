export interface GroupSummary {
  id: string
  waId: string
  name: string
  pictureUrl: string | null
  isAnnouncementGroup: boolean
  memberCount: number
  memberLimit: number | null
  pendingRequestCount: number
}

export interface GroupDetail extends GroupSummary {
  description: string | null
  communityId: string
  communityName: string
  rawMetadata?: unknown
}

export type MembershipStatus = 'member' | 'pending'

export interface GroupMemberRow {
  memberId: string
  waId: string
  displayName: string
  avatarUrl: string | null
  isAdmin: boolean
  isSuperAdmin: boolean
  status: MembershipStatus
  joinedAt: string
}

export interface GroupJoinRequest {
  memberId: string
  waId: string
  displayName: string
  requestedAt: string
}

export type GroupDetailTab = 'overview' | 'members' | 'requests' | 'advanced'
