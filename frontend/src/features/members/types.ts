export interface CommunityMemberRow {
  id: string
  waId: string
  displayName: string
  avatarUrl: string | null
  phoneNumberMasked: string
  isAdmin: boolean
  isCommunityAdmin: boolean
  groupCount: number
  joinedAt: string | null
}

export type MembershipStatus = 'member' | 'pending'

export interface MemberMembership {
  groupId: string
  groupName: string
  communityId: string
  communityName: string
  isAdmin: boolean
  status: MembershipStatus
  joinedAt: string | null
}

export interface MemberDetail {
  id: string
  waId: string
  displayName: string
  phoneNumberMasked: string
  avatarUrl: string | null
  isBusiness: boolean
  firstSeenAt: string
  memberships: MemberMembership[]
}
