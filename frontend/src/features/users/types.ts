import type { UserRole } from '@/features/auth/types'

export interface ManagedUser {
  id: string
  username: string
  role: UserRole
  isActive: boolean
  createdAt: string
  totpEnabled: boolean
  /** Non-`null` only for an auto-provisioned `group_admin` account — the
   * WhatsApp identity (`Member`) this account is linked to. */
  memberId: string | null
  /** `false` only for an unclaimed, auto-provisioned `group_admin` account
   * waiting on its owner to complete `/claim` — see `ClaimPage.tsx`. */
  isClaimed: boolean
  /** `false` for a newly-discovered `group_admin` account no owner has
   * reviewed yet — nothing is ever sent to them until an owner explicitly
   * approves (see `UsersPage.tsx`'s "Approve" action). `true` for every
   * owner/admin/viewer account by construction. */
  isApproved: boolean
  claimedAt: string | null
  /** `null` for every owner/admin/viewer account — set for a `group_admin`
   * account so a send-confirmation dialog can show who a message goes to. */
  phoneNumberMasked: string | null
}

export interface CreateUserInput {
  username: string
  password: string
  role: UserRole
}

export interface UpdateUserInput {
  role?: UserRole
  isActive?: boolean
}
