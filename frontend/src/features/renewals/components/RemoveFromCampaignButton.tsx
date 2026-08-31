import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { HelpTooltip } from '@/components/ui/help-tooltip'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useRemoveFromCampaign } from '../queries'
import type { RenewalConfirmation } from '../types'

/** Stops tracking one member in a campaign — a Communeer-only bookkeeping
 * action, distinct from (and never triggering) a WhatsApp removal. Shared
 * between `ConfirmationsTable` and `NonRespondersTab`, since "I don't need
 * to keep tracking this person" is a valid call from either view. */
export function RemoveFromCampaignButton({
  campaignId,
  confirmation,
  isViewer,
}: {
  campaignId: string
  confirmation: RenewalConfirmation
  isViewer: boolean
}) {
  const removeFromCampaign = useRemoveFromCampaign(campaignId)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const isBusy = removeFromCampaign.isPending && removeFromCampaign.variables === confirmation.memberId

  if (isViewer) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button size="icon-sm" variant="ghost" disabled>
              <Trash2 className="size-3.5" />
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>Your role doesn't have access to this</TooltipContent>
      </Tooltip>
    )
  }

  return (
    <>
      <HelpTooltip content="Stop tracking this member here">
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Remove from this campaign"
          disabled={isBusy}
          onClick={() => setConfirmOpen(true)}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </HelpTooltip>
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove {confirmation.displayName} from this campaign?</DialogTitle>
            <DialogDescription>
              This only stops tracking them here — it doesn't remove them from WhatsApp or undo a reply/reaction
              they already sent.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={isBusy}
              onClick={() => {
                removeFromCampaign.mutate(confirmation.memberId, { onSuccess: () => setConfirmOpen(false) })
              }}
            >
              {isBusy ? 'Removing…' : 'Remove'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
