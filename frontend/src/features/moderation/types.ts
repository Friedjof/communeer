/**
 * Cross-signal moderation queue: read-only aggregation over already-synced
 * data. Communeer never sends a WhatsApp message, reads a reaction, or
 * removes anyone on its own — every section here is a candidate list to act
 * on manually in WhatsApp, same posture as renewals.
 */

/** A group where at most one member is admin — a single point of failure. */
export interface AdminCoverageGap {
  groupId: string
  groupName: string
  adminCount: number
}

/** A community member (any of their groups) who has never posted a message, excluding admins. */
export interface NeverActiveMember {
  memberId: string
  waId: string
  displayName: string
  avatarUrl: string | null
  phoneNumberMasked: string | null
  groupCount: number
  joinedAt: string | null
}

/** A group where an unusually high share of current members joined very recently. */
export interface JoinBurst {
  groupId: string
  groupName: string
  memberCount: number
  recentJoinCount: number
}

export type CapacityAttentionReason = 'capacity' | 'requests' | 'both'

/** A group at/above the capacity-attention threshold, or with pending join requests. */
export interface CapacityAttention {
  groupId: string
  groupName: string
  memberCount: number
  memberLimit: number | null
  pendingRequestCount: number
  percentFull: number | null
  reason: CapacityAttentionReason
}

export interface ModerationQueue {
  adminCoverageGaps: AdminCoverageGap[]
  neverActiveMembers: NeverActiveMember[]
  joinBursts: JoinBurst[]
  capacityAttention: CapacityAttention[]
}

/** The four moderation-queue sections — mirrors the backend's `MODERATION_SECTIONS` exactly. */
export type ModerationSection = 'admin_coverage_gaps' | 'never_active_members' | 'join_bursts' | 'capacity_attention'
