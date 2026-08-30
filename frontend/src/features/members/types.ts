import type { ActivityType } from '@/components/data/ActivityBar'

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
  /** Last time this member actually posted a message — a verified signal, `null` means never posted. */
  lastMessageAt: string | null
  /** Almost always `null`: WhatsApp doesn't expose presence/read data for most accounts. */
  lastSeenAt: string | null
  /** Unified "last activity" (message/reaction/view), live-updated via the WPPConnect webhook. */
  lastActivityType: ActivityType | null
  lastActivityAt: string | null
  lastActivityContent: string | null
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
  lastActivityType: ActivityType | null
  lastActivityAt: string | null
  lastActivityContent: string | null
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
