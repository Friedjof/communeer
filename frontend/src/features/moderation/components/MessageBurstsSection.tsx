import { useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Flame, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { EmptyState } from '@/components/feedback/EmptyState'
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
import { useRemoveGroupMember } from '@/features/groups/queries'
import { moderationKeys, useDismissModerationItem } from '../queries'
import type { MessageBurst } from '../types'
import { isModerationItemDismissing, MODERATION_ROW_TRIGGER_CLASS } from './moderationRowHelpers'
import { ModerationRow } from './ModerationRow'
import { ModerationSectionCard } from './ModerationSectionCard'

interface MessageBurstsSectionProps {
  communityId: string
  bursts: MessageBurst[]
}

export function MessageBurstsSection({ communityId, bursts }: MessageBurstsSectionProps) {
  const dismiss = useDismissModerationItem(communityId)

  return (
    <ModerationSectionCard
      title="Message bursts"
      description="Members posting unusually fast right now — a live signal over the last few minutes, not a scan of their full history."
    >
      {bursts.length === 0 ? (
        <EmptyState
          icon={Flame}
          title="No message bursts"
          description="No member is posting unusually fast right now."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {bursts.map((burst, index) => (
            <MessageBurstRow
              key={burst.groupMembershipId}
              communityId={communityId}
              burst={burst}
              index={index}
              dismiss={dismiss}
            />
          ))}
        </ul>
      )}
    </ModerationSectionCard>
  )
}

interface MessageBurstRowProps {
  communityId: string
  burst: MessageBurst
  index: number
  dismiss: ReturnType<typeof useDismissModerationItem>
}

function MessageBurstRow({ communityId, burst, index, dismiss }: MessageBurstRowProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const queryClient = useQueryClient()
  const remove = useRemoveGroupMember(burst.groupId)

  return (
    <ModerationRow
      index={index}
      isDismissing={isModerationItemDismissing(dismiss, burst.groupMembershipId)}
      onDismiss={() => dismiss.mutate({ section: 'message_bursts', targetId: burst.groupMembershipId })}
      actions={
        <>
          <HelpTooltip content="Remove this member from the group">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Remove"
              disabled={remove.isPending}
              onClick={() => setConfirmOpen(true)}
            >
              <Trash2 className="size-4" />
            </Button>
          </HelpTooltip>
          <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Remove {burst.memberDisplayName}?</DialogTitle>
                <DialogDescription>
                  This removes them from &ldquo;{burst.groupName}&rdquo; in WhatsApp. This action can&apos;t be undone
                  from here.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  disabled={remove.isPending}
                  onClick={() => {
                    remove.mutate(burst.memberId, {
                      onSuccess: () => {
                        setConfirmOpen(false)
                        void queryClient.invalidateQueries({ queryKey: moderationKeys.queue(communityId) })
                      },
                    })
                  }}
                >
                  {remove.isPending ? 'Removing…' : 'Remove'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </>
      }
    >
      <Link
        to="/c/$communityId/groups/$groupId"
        params={{ communityId, groupId: burst.groupId }}
        search={{ tab: 'messages' }}
        className={MODERATION_ROW_TRIGGER_CLASS}
      >
        <div className="flex items-center gap-2">
          <Flame className="size-4 shrink-0 text-destructive" />
          <span className="font-medium">{burst.memberDisplayName}</span>
          <span className="text-muted-foreground">in {burst.groupName}</span>
        </div>
        <span className="text-muted-foreground">
          {burst.messageCount} messages in the last {burst.windowMinutes} min
        </span>
      </Link>
    </ModerationRow>
  )
}
