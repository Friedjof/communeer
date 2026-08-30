import { HelpCircle, MessageCircle, MessageCircleOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatRelative } from '@/lib/format'

/**
 * Renders a member's real, verified activity signal: `lastMessageAt` comes
 * from actual observed message history, so `null` genuinely means "never
 * posted" — a confirmed fact, not a placeholder for missing data. Never
 * style this the same as an "unknown"/"not available" state (see
 * `ActivityColumnHeader` for why `lastSeenAt` isn't rendered the same way).
 */
export function MessageActivityBadge({ lastMessageAt }: { lastMessageAt: string | null }) {
  if (!lastMessageAt) {
    return (
      <Badge variant="outline" className="gap-1 border-amber-500/30 text-amber-600 dark:text-amber-400">
        <MessageCircleOff className="size-3" />
        Never posted
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1 text-muted-foreground">
      <MessageCircle className="size-3" />
      {formatRelative(lastMessageAt)}
    </Badge>
  )
}

/**
 * Header for the activity column. Only `lastMessageAt` (real message
 * history) is shown as a column — `lastSeenAt` (presence/read receipts) is
 * almost always `null` in practice (verified live against a real connected
 * account: WhatsApp doesn't expose it for most accounts), so a dedicated
 * column for it would just repeat the same "not available" placeholder on
 * every row. This tooltip explains that omission honestly instead of
 * silently dropping the field.
 */
export function ActivityColumnHeader() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help items-center gap-1">
          Activity
          <HelpCircle className="size-3 text-muted-foreground" />
        </span>
      </TooltipTrigger>
      <TooltipContent>
        Last verified message from this member. WhatsApp doesn't expose "last seen"/read-receipt data for most
        accounts, so that signal isn't shown here.
      </TooltipContent>
    </Tooltip>
  )
}
