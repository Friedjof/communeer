import { EyeOff, MessageCircle, SmilePlus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatRelative } from '@/lib/format'

export type ActivityType = 'message' | 'reaction' | 'view'

/**
 * WhatsApp doesn't expose a read-receipt/"seen" event for other people's
 * messages (verified live, see `MessageActivityCell.tsx`'s
 * `ActivityColumnHeader` for the same honest posture) — `view` stays in the
 * type union for structural completeness, but is never actually populated
 * by the backend today. Shown here so the explanation is available if it
 * ever is.
 */
const VIEW_EXPLANATION =
  'WhatsApp doesn\'t expose "last seen"/read-receipt data for most accounts, so that signal isn\'t shown here.'

function truncate(text: string, limit: number | null): string {
  if (limit === null || text.length <= limit) return text
  return `${text.slice(0, limit)}…`
}

interface ActivityBarProps {
  lastActivityType: ActivityType | null
  lastActivityAt: string | null
  lastActivityContent: string | null
  /**
   * Max characters shown before truncating with an ellipsis. Pass `null`
   * for the full, untruncated text (e.g. with `showContentInline`, where
   * there's room for it). Defaults to a compact 80 chars for table cells.
   */
  truncateAt?: number | null
  /**
   * Show the activity content as a visible line of text next to the badge,
   * instead of only inside a hover-only tooltip. A tooltip is easy to miss
   * (and unusable on touch) in a context that otherwise has plenty of room
   * to just show the content directly — e.g. the member detail dialog.
   * Table cells keep the compact, tooltip-only default.
   */
  showContentInline?: boolean
}

/**
 * Unified "last activity" signal: whichever of message / reaction / view
 * was most recently observed, with a type-specific icon, relative time, and
 * a tooltip carrying the actual content (message text / reaction emoji).
 * `null` (nothing observed yet) renders as a neutral, non-alarming "no
 * activity" state — this is different from `MessageActivityBadge`'s
 * amber "Never posted" (a real, currently-still-relevant renewal signal for
 * `lastMessageAt` specifically), since "no unified activity yet" isn't
 * necessarily meaningful on its own.
 */
export function ActivityBar({
  lastActivityType,
  lastActivityAt,
  lastActivityContent,
  truncateAt = 80,
  showContentInline = false,
}: ActivityBarProps) {
  if (lastActivityType === null || !lastActivityAt) {
    return (
      <Badge variant="outline" className="gap-1 text-muted-foreground">
        <EyeOff className="size-3" />
        No activity
      </Badge>
    )
  }

  if (lastActivityType === 'view') {
    const badge = (
      <Badge variant="outline" className="w-fit cursor-help gap-1 text-muted-foreground">
        <EyeOff className="size-3" />
        {formatRelative(lastActivityAt)}
      </Badge>
    )
    if (showContentInline) {
      return (
        <div className="flex flex-col gap-1">
          {badge}
          <p className="text-sm italic text-muted-foreground">{VIEW_EXPLANATION}</p>
        </div>
      )
    }
    return (
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent>{VIEW_EXPLANATION}</TooltipContent>
      </Tooltip>
    )
  }

  const Icon = lastActivityType === 'reaction' ? SmilePlus : MessageCircle
  const fallback = lastActivityType === 'reaction' ? 'Reacted' : 'No message text available.'
  const content = lastActivityContent ? truncate(lastActivityContent, truncateAt) : fallback

  const badge = (
    <Badge variant="outline" className="w-fit cursor-help gap-1 text-muted-foreground">
      <Icon className="size-3" />
      {formatRelative(lastActivityAt)}
    </Badge>
  )

  if (showContentInline) {
    return (
      <div className="flex flex-col gap-1">
        {badge}
        <p className={`break-words text-sm ${lastActivityContent ? '' : 'italic text-muted-foreground'}`}>
          {lastActivityContent ? `"${content}"` : content}
        </p>
      </div>
    )
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{badge}</TooltipTrigger>
      <TooltipContent className="max-w-xs break-words">{content}</TooltipContent>
    </Tooltip>
  )
}
