import { format } from 'date-fns'

/**
 * Mirrors `build_renewal_reminder_message` in
 * `backend/communeer/renewals/service.py` (lines 78-96) line for line —
 * this is what actually gets sent, so a send-confirmation dialog can show
 * the real text instead of a paraphrase. If the backend template ever
 * changes, this must be updated to match.
 */
export function buildRenewalReminderPreview(groupName: string, deadline: string | Date): string {
  const deadlineStr = format(typeof deadline === 'string' ? new Date(deadline) : deadline, 'dd.MM.yyyy')
  return (
    `Hallo! 👋 Wir prüfen gerade, wer in *${groupName}* weiterhin dabei sein möchte.\n` +
    `Reagiere mit 👍 auf diese Nachricht, wenn du weiterhin dabei sein möchtest, oder mit ❌, ` +
    `wenn nicht mehr — bis spätestens ${deadlineStr}. Eine Antwort auf diese Nachricht geht ` +
    `auch, das dauert dann aber etwas länger.\n` +
    `Falls wir nichts von dir hören, wird deine Mitgliedschaft überprüft.\n` +
    `\n—\n\n` +
    `Hi! 👋 We're checking in on who'd like to stay part of *${groupName}*.\n` +
    `React 👍 to this message if you'd like to stay, or ❌ if not — by ${deadlineStr} at the ` +
    `latest. Replying works too, it'll just take a bit longer.\n` +
    `If we don't hear from you, your membership will be reviewed.`
  )
}
