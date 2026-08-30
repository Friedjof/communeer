import type { ActivityType } from '@/components/data/ActivityBar'

export interface GroupSummary {
  id: string
  waId: string
  name: string
  description: string | null
  pictureUrl: string | null
  isAnnouncementGroup: boolean
  memberCount: number
  memberLimit: number | null
  pendingRequestCount: number
  adminCount: number
  /** Most recent message activity across the group's members, `null` means never observed. */
  lastMessageAt: string | null
}

export interface GroupDetail extends GroupSummary {
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
  /** Last time this member actually posted a message — a verified signal, `null` means never posted. */
  lastMessageAt: string | null
  /** Almost always `null`: WhatsApp doesn't expose presence/read data for most accounts. */
  lastSeenAt: string | null
  /** Unified "last activity" (message/reaction/view), live-updated via the WPPConnect webhook. */
  lastActivityType: ActivityType | null
  lastActivityAt: string | null
  lastActivityContent: string | null
}

export interface GroupJoinRequest {
  memberId: string
  waId: string
  displayName: string
  requestedAt: string
}

export type GroupDetailTab = 'overview' | 'members' | 'requests' | 'advanced'
