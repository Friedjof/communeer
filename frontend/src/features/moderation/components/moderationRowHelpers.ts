import type { useDismissModerationItem } from '../queries'

/** Shared trigger styling for a row's clickable content — a `Link` in most
 * sections, a plain `button` in `NeverActiveMembersSection` (it opens a
 * dialog instead of navigating), so the element type stays up to the
 * caller while the visual style stays identical. */
export const MODERATION_ROW_TRIGGER_CLASS =
  'flex flex-1 items-center justify-between gap-3 rounded-lg border p-3 text-sm transition-colors hover:bg-muted/60'

/** Whether the dismiss mutation is currently in flight for this specific
 * row's target — the same check every moderation section repeated. */
export function isModerationItemDismissing(
  dismiss: Pick<ReturnType<typeof useDismissModerationItem>, 'isPending' | 'variables'>,
  targetId: string,
): boolean {
  return dismiss.isPending && dismiss.variables?.targetId === targetId
}
