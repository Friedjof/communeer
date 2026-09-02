import { ShieldMinus, ShieldPlus, Trash2 } from 'lucide-react'
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
import { useSession } from '@/features/auth/queries'
import { useDemoteGroupMember, usePromoteGroupMember, useRemoveGroupMember } from '@/features/groups/queries'
import type { GroupMemberRow } from '@/features/groups/types'

interface GroupMemberRowActionsProps {
  groupId: string
  member: GroupMemberRow
}

/** Ghost-icon-button row actions for a group's member table — promote/demote
 * toggle plus remove (with a confirm step, since removal is destructive and
 * irreversible from this UI). Mirrors `ModerationRow.tsx`'s row-action
 * styling. Stops click propagation so it doesn't also trigger the row's
 * `onRowClick` (opens `MemberDetailDialog`). */
export function GroupMemberRowActions({ groupId, member }: GroupMemberRowActionsProps) {
  const [confirmRemoveOpen, setConfirmRemoveOpen] = useState(false)
  const session = useSession()
  const canManage =
    session.data?.role === 'owner' || session.data?.role === 'admin' || session.data?.role === 'group_admin'
  const promote = usePromoteGroupMember(groupId)
  const demote = useDemoteGroupMember(groupId)
  const remove = useRemoveGroupMember(groupId)

  if (!canManage) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="text-xs text-muted-foreground">—</span>
        </TooltipTrigger>
        <TooltipContent>Your role doesn't have access to this</TooltipContent>
      </Tooltip>
    )
  }

  const isBusy = promote.isPending || demote.isPending || remove.isPending

  return (
    <div className="flex justify-end gap-1" onClick={(event) => event.stopPropagation()}>
      {member.isAdmin ? (
        <HelpTooltip content="Remove this member's admin rights in the group">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Demote"
            disabled={isBusy}
            onClick={() => demote.mutate(member.memberId)}
          >
            <ShieldMinus className="size-4" />
          </Button>
        </HelpTooltip>
      ) : (
        <HelpTooltip content="Make this member an admin in the group">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Promote"
            disabled={isBusy}
            onClick={() => promote.mutate(member.memberId)}
          >
            <ShieldPlus className="size-4" />
          </Button>
        </HelpTooltip>
      )}
      <HelpTooltip content="Remove this member from the group">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Remove"
          disabled={isBusy}
          onClick={() => setConfirmRemoveOpen(true)}
        >
          <Trash2 className="size-4" />
        </Button>
      </HelpTooltip>

      <Dialog open={confirmRemoveOpen} onOpenChange={setConfirmRemoveOpen}>
        <DialogContent onClick={(event) => event.stopPropagation()}>
          <DialogHeader>
            <DialogTitle>Remove {member.displayName}?</DialogTitle>
            <DialogDescription>
              This removes them from the group in WhatsApp. This action can't be undone from here.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRemoveOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                remove.mutate(member.memberId, { onSuccess: () => setConfirmRemoveOpen(false) })
              }}
            >
              {remove.isPending ? 'Removing…' : 'Remove'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
