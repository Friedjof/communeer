import { Check, Copy, Link2 } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { HelpTooltip } from '@/components/ui/help-tooltip'
import { useGroupInviteLink } from '../queries'

/** Fetched on demand only (see `useGroupInviteLink`) — `null` is a real,
 * honest answer (the connected account can't generate one for this group
 * right now), not an error, so it's shown as plain text rather than an
 * `ErrorState`. */
export function GroupInviteLink({ groupId }: { groupId: string }) {
  const inviteLink = useGroupInviteLink(groupId)
  const [copied, setCopied] = useState(false)

  async function handleCopy(link: string) {
    await navigator.clipboard.writeText(link)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!inviteLink.isFetched) {
    return (
      <Button variant="outline" size="sm" className="gap-1.5" onClick={() => inviteLink.refetch()} disabled={inviteLink.isFetching}>
        <Link2 className="size-3.5" />
        {inviteLink.isFetching ? 'Fetching…' : 'Get invite link'}
      </Button>
    )
  }

  if (inviteLink.isError || !inviteLink.data?.inviteLink) {
    return <p className="text-xs text-muted-foreground">No invite link available for this group right now.</p>
  }

  const link = inviteLink.data.inviteLink
  return (
    <div className="flex items-center gap-1.5">
      <p className="truncate font-mono text-xs">{link}</p>
      <HelpTooltip content="Copy invite link to clipboard">
        <Button variant="ghost" size="icon-sm" aria-label="Copy invite link" onClick={() => handleCopy(link)}>
          {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
        </Button>
      </HelpTooltip>
    </div>
  )
}
