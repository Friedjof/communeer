import { apiGet, apiPost } from '@/api/client'
import type {
  CompleteClaimInput,
  LoginResult,
  RecoveryCodes,
  SessionUser,
  TotpSetup,
  WhatsAppOtpEnableResult,
  WhatsAppOtpSetup,
} from './types'

interface LoginTotpRequiredBody {
  requiresTotp: true
  totpEnabled: boolean
  whatsappOtpEnabled: boolean
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const body = await apiPost<SessionUser | LoginTotpRequiredBody>('/auth/login', { username, password })
  if ('requiresTotp' in body && body.requiresTotp) {
    return { requiresTotp: true, totpEnabled: body.totpEnabled, whatsappOtpEnabled: body.whatsappOtpEnabled }
  }
  return { requiresTotp: false, user: body as SessionUser }
}

export function verifyLoginTotp(code: string): Promise<SessionUser> {
  return apiPost<SessionUser>('/auth/login/verify-totp', { code })
}

export function requestLoginWhatsappOtp(): Promise<void> {
  return apiPost<void>('/auth/login/whatsapp-otp/request')
}

export function verifyLoginWhatsappOtp(code: string): Promise<SessionUser> {
  return apiPost<SessionUser>('/auth/login/whatsapp-otp/verify', { code })
}

export function logout(): Promise<void> {
  return apiPost<void>('/auth/logout')
}

export function getSession(): Promise<SessionUser> {
  return apiGet<SessionUser>('/session')
}

export function setupTotp(): Promise<TotpSetup> {
  return apiPost<TotpSetup>('/auth/2fa/setup')
}

export function enableTotp(code: string): Promise<RecoveryCodes> {
  return apiPost<RecoveryCodes>('/auth/2fa/enable', { code })
}

export function disableTotp(password: string): Promise<void> {
  return apiPost<void>('/auth/2fa/disable', { password })
}

export function regenerateRecoveryCodes(password: string): Promise<RecoveryCodes> {
  return apiPost<RecoveryCodes>('/auth/2fa/recovery-codes/regenerate', { password })
}

export function setupWhatsAppOtp(phoneNumber: string): Promise<WhatsAppOtpSetup> {
  return apiPost<WhatsAppOtpSetup>('/auth/2fa/whatsapp/setup', { phoneNumber })
}

export function enableWhatsAppOtp(code: string): Promise<WhatsAppOtpEnableResult> {
  return apiPost<WhatsAppOtpEnableResult>('/auth/2fa/whatsapp/enable', { code })
}

export function disableWhatsAppOtp(password: string): Promise<void> {
  return apiPost<void>('/auth/2fa/whatsapp/disable', { password })
}

export function requestClaim(phoneNumber: string): Promise<void> {
  return apiPost<void>('/auth/claim/request', { phoneNumber })
}

export function completeClaim(input: CompleteClaimInput): Promise<SessionUser> {
  return apiPost<SessionUser>('/auth/claim/complete', input)
}
