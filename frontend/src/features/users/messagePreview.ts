/**
 * Mirrors `build_whatsapp_otp_message` in `backend/communeer/auth/security.py`
 * (lines 175-181) — the same template used for both the login-OTP message
 * and the claim-code message an owner sends by approving/resending (see
 * `auth/provisioning.py::send_claim_code`). The 6-digit code is generated
 * server-side only at send time, so it can't be shown for real here —
 * `CODE_PLACEHOLDER` stands in for it. If the backend template ever
 * changes, this must be updated to match.
 */
export const CODE_PLACEHOLDER = '••••••'

export const CLAIM_CODE_MESSAGE_PREVIEW =
  `Dein Communeer-Anmeldecode ist ${CODE_PLACEHOLDER}. Er läuft in 5 Minuten ab. ` +
  `Teile diesen Code mit niemandem.\n\n` +
  `Hi! Your Communeer login code is ${CODE_PLACEHOLDER}. It expires in 5 minutes. ` +
  `Never share this code with anyone.`
