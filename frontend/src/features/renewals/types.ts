/**
 * Renewal campaigns are a manual-tracking tool: the admin posts the
 * "please confirm you still live here" message in WhatsApp themselves, and
 * marks people confirmed here after observing their reply/reaction.
 * Communeer never sends messages or detects reactions automatically.
 */

/** A candidate for a renewal round. The backend already excludes admins. */
export interface RenewalSuggestion {
  memberId: string
  waId: string
  displayName: string
  avatarUrl: string | null
  phoneNumberMasked: string
  groupCount: number
  joinedAt: string | null
  /**
   * Last time this member actually posted a message, aggregated from real
   * message history. `null` genuinely means "never posted" — a verified
   * signal, not a placeholder.
   */
  lastMessageAt: string | null
  /**
   * Last known presence/read signal. Almost always `null` in practice —
   * WhatsApp doesn't expose per-message read receipts or reliable presence
   * data for most accounts (verified live against a real connected
   * account). `null` here means "not available", a different reason than
   * `lastMessageAt`'s `null` ("never posted").
   */
  lastSeenAt: string | null
}

/** Summary counters for one campaign, as returned by list/detail/create endpoints. */
export interface RenewalCampaignSummary {
  id: string
  communityId: string
  startedAt: string
  deadline: string
  pendingCount: number
  confirmedCount: number
  expiredCount: number
  totalCount: number
}

export type RenewalConfirmationStatus = 'pending' | 'confirmed'

/**
 * A single member's confirmation row. `status` is only ever `pending` or
 * `confirmed` in storage — "expired"/"overdue" is a computed `isExpired`
 * flag on an otherwise-pending row once the deadline has passed, not a
 * third status value.
 */
export interface RenewalConfirmation {
  memberId: string
  waId: string
  displayName: string
  status: RenewalConfirmationStatus
  isExpired: boolean
  respondedAt: string | null
}

export interface RenewalCampaignDetail extends RenewalCampaignSummary {
  confirmations: RenewalConfirmation[]
}

export interface CreateRenewalCampaignInput {
  memberIds: string[]
  deadlineDays?: number
}
