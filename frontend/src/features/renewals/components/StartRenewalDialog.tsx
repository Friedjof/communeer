import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useCreateRenewalCampaign } from '../queries'
import type { RenewalSuggestion } from '../types'
import { initials } from '@/lib/format'

interface StartRenewalDialogProps {
  groupId: string
  members: RenewalSuggestion[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (campaignId: string) => void
}

const DEFAULT_DEADLINE_DAYS = 7

export function StartRenewalDialog({ groupId, members, open, onOpenChange, onCreated }: StartRenewalDialogProps) {
  const [deadlineDays, setDeadlineDays] = useState(DEFAULT_DEADLINE_DAYS)
  const createCampaign = useCreateRenewalCampaign(groupId)

  function handleOpenChange(next: boolean) {
    if (!next) {
      createCampaign.reset()
      setDeadlineDays(DEFAULT_DEADLINE_DAYS)
    }
    onOpenChange(next)
  }

  function handleConfirm() {
    createCampaign.mutate(
      { memberIds: members.map((member) => member.memberId), deadlineDays },
      {
        onSuccess: (campaign) => {
          handleOpenChange(false)
          onCreated(campaign.id)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2">
            <DialogTitle>Start a renewal round for {members.length} member{members.length === 1 ? '' : 's'}</DialogTitle>
            <Badge variant="secondary" className="gap-1">
              <Sparkles className="size-3" />
              Automated
            </Badge>
          </div>
          <DialogDescription>
            This creates a tracking list and sends a reminder — review it before continuing.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-start gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
          <p>
            Communeer automatically sends each member a reminder (in German and English) explaining how to confirm.
            If someone reacts <strong>❌</strong> to it, that's read automatically and counts as "no longer
            interested" — they're immediately treated as expired, no need to wait for the deadline. Removing anyone
            from WhatsApp still stays a manual step.
          </p>
        </div>

        <div className="flex max-h-48 flex-col gap-2 overflow-y-auto rounded-lg border p-2">
          {members.map((member) => (
            <div key={member.memberId} className="flex items-center gap-2.5">
              <Avatar className="size-7">
                <AvatarFallback className="text-xs">{initials(member.displayName)}</AvatarFallback>
              </Avatar>
              <div className="flex flex-col">
                <span className="text-sm font-medium leading-tight">{member.displayName}</span>
                <span className="text-xs text-muted-foreground leading-tight">{member.phoneNumberMasked}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="deadline-days" className="text-sm font-medium">
            Deadline (days)
          </label>
          <Input
            id="deadline-days"
            type="number"
            min={1}
            max={90}
            value={deadlineDays}
            onChange={(event) => setDeadlineDays(Math.max(1, Number(event.target.value) || DEFAULT_DEADLINE_DAYS))}
            className="w-20"
          />
        </div>

        {createCampaign.isError ? (
          <p className="text-sm text-destructive">{createCampaign.error.message}</p>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleConfirm} disabled={createCampaign.isPending}>
            {createCampaign.isPending ? 'Creating…' : `Start tracking for ${members.length} member${members.length === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
