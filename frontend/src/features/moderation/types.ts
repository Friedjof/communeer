/**
 * Cross-signal moderation queue: read-only aggregation over already-synced
 * data. Communeer never sends a WhatsApp message, reads a reaction, or
 * removes anyone on its own — every section here is a candidate list, most
 * now actionable inline (approve/reject a request, remove a member) via the
 * same mutations `features/groups` already exposes, same posture as
 * renewals.
 */

import type { GroupJoinRequest } from '@/features/groups/types'

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
  /** Populated only when `reason` is "requests"/"both" — lets this section's
   * rows be approved/rejected inline instead of only linking into the
   * group's Requests tab. */
  pendingRequests: GroupJoinRequest[]
}

/** A member posting unusually fast right now (a live snapshot over the last
 * few minutes, not a retrospective scan) — the one section whose target is a
 * `GroupMembership`, not a bare group or member, since the signal is
 * inherently a (group, member) pair. */
export interface MessageBurst {
  groupMembershipId: string
  groupId: string
  groupName: string
  memberId: string
  memberDisplayName: string
  memberAvatarUrl: string | null
  messageCount: number
  windowMinutes: number
}

/** A member repeating the exact same message text within the last 24h. */
export interface DuplicateContent {
  groupMembershipId: string
  groupId: string
  groupName: string
  memberId: string
  memberDisplayName: string
  contentPreview: string
  occurrenceCount: number
}

export interface ModerationQueue {
  adminCoverageGaps: AdminCoverageGap[]
  neverActiveMembers: NeverActiveMember[]
  joinBursts: JoinBurst[]
  capacityAttention: CapacityAttention[]
  messageBursts: MessageBurst[]
  duplicateContent: DuplicateContent[]
}

/** The six moderation-queue sections — mirrors the backend's `MODERATION_SECTIONS` exactly. */
export type ModerationSection =
  | 'admin_coverage_gaps'
  | 'never_active_members'
  | 'join_bursts'
  | 'capacity_attention'
  | 'message_bursts'
  | 'duplicate_content'
