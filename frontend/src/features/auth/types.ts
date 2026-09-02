export type UserRole = 'owner' | 'admin' | 'group_admin' | 'viewer'

export interface SessionUser {
  id: string
  username: string
  role: UserRole
  totpEnabled: boolean
  whatsappOtpEnabled: boolean
}

/** `role === 'owner' | 'admin' | 'group_admin'` require at least one 2FA
 * factor (TOTP and/or WhatsApp-OTP) to use anything beyond login and the
 * 2FA setup routes themselves (see backend `deps.get_current_user`) — a
 * freshly-claimed `group_admin` account (see `ClaimPage.tsx`) has neither
 * factor enabled yet, same as a brand-new owner/admin. */
export function isTotpRequired(role: UserRole): boolean {
  return role === 'owner' || role === 'admin' || role === 'group_admin'
}

export type LoginResult =
  | { requiresTotp: true; totpEnabled: boolean; whatsappOtpEnabled: boolean }
  | { requiresTotp: false; user: SessionUser }

export interface RecoveryCodes {
  recoveryCodes: string[]
}

export interface TotpSetup {
  secret: string
  otpauthUri: string
}

export interface WhatsAppOtpSetup {
  phoneWaId: string
}

export interface WhatsAppOtpEnableResult {
  /** `null` when an existing valid set from another factor was preserved
   * instead of being replaced — see `auth/service.py::enable_whatsapp_otp`. */
  recoveryCodes: string[] | null
}

export interface CompleteClaimInput {
  phoneNumber: string
  code: string
  username?: string
  password: string
}
