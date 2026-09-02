import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { HelpTooltip } from '@/components/ui/help-tooltip'

// A never-active-members list can genuinely have thousands of rows in a
// real community — capping the stagger (same cap `DataTable.tsx` uses)
// keeps the animation confined to what's visible on first paint. Without
// this, `animation-fill-mode: backwards` combined with an uncapped
// `index * delay` left far-down rows sitting invisible for tens of
// seconds, which looked like broken/empty rows, not "still animating in".
const MAX_STAGGERED_ROWS = 15

interface ModerationRowProps {
  isDismissing: boolean
  onDismiss: () => void
  /** The row's clickable content — a `Link` or `button` styled with
   * `MODERATION_ROW_TRIGGER_CLASS`. */
  children: ReactNode
  /** Extra inline mutating action(s) (approve/reject, remove…) rendered
   * between `children` and the dismiss button — same ghost-icon-button
   * styling. Optional: most sections still only offer dismiss + navigate. */
  actions?: ReactNode
  /** Position within its section's list — used to stagger the entrance
   * animation for the first `MAX_STAGGERED_ROWS` rows; every row past that
   * renders immediately, no delay. */
  index?: number
}

/** Shared row wrapper + dismiss button for a moderation queue item. */
export function ModerationRow({ isDismissing, onDismiss, children, actions, index = 0 }: ModerationRowProps) {
  const staggerIndex = Math.min(index, MAX_STAGGERED_ROWS)
  return (
    <li
      className="flex animate-in items-center gap-2 fade-in slide-in-from-bottom-1 duration-200"
      style={{ animationDelay: `${staggerIndex * 30}ms`, animationFillMode: 'backwards' }}
    >
      {children}
      {actions}
      <HelpTooltip content="Dismiss until this gets worse">
        <Button variant="ghost" size="icon-sm" aria-label="Dismiss" disabled={isDismissing} onClick={onDismiss}>
          <X className="size-4" />
        </Button>
      </HelpTooltip>
    </li>
  )
}
