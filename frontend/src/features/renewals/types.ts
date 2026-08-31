/**
 * Renewal campaigns are scoped to a single group (a member can belong to
 * several groups in the same community, and a renewal round only ever
 * concerns their standing in one of them). Starting one sends a bilingual
 * (German/English) reminder DM to every selected member, and reacting ❌ to
 * that message is read automatically and treated as an immediate decline
 * (see `declinedAt`). Confirming is still a manual step — an admin marks
 * someone confirmed after seeing their reply. Removal from the group is also
 * manual: an admin clicks "Process removals" to remove everyone currently
 * declined or past the deadline in one batch (see `removedAt`) — nothing
 * removes anyone automatically.
 */

/** A candidate for a renewal round. The backend already excludes this group's admins. */
export interface RenewalSuggestion {
  memberId: string
  waId: string
  displayName: string
  avatarUrl: string | null
  phoneNumberMasked: string
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
  groupId: string
  startedAt: string
  deadline: string
  pendingCount: number
  confirmedCount: number
  expiredCount: number
  totalCount: number
  /** Set once an admin archives the campaign — never set automatically, even
   * when `totalCount` reaches zero. Only an archived campaign can be deleted. */
  archivedAt: string | null
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
  /** When the bilingual reminder DM was last (re)sent — `null` means it
   * hasn't gone out yet (never attempted, or the attempt failed). */
  reminderSentAt: string | null
  /** Set the moment the member reacts ❌ to the reminder — an explicit
   * "no longer interested" signal, distinct from simply missing the
   * deadline (though both make `isExpired` true). */
  declinedAt: string | null
  /** Set once "Process removals" has actually removed this member from the
   * campaign's group — `null` means they're still in the group, whether or
   * not they're currently declined/expired. */
  removedAt: string | null
}

export interface RenewalCampaignDetail extends RenewalCampaignSummary {
  confirmations: RenewalConfirmation[]
}

export interface CreateRenewalCampaignInput {
  memberIds: string[]
  deadlineDays?: number
}
