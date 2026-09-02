import { useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Copy, Trash2 } from 'lucide-react'
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
import type { DuplicateContent } from '../types'
import { isModerationItemDismissing, MODERATION_ROW_TRIGGER_CLASS } from './moderationRowHelpers'
import { ModerationRow } from './ModerationRow'
import { ModerationSectionCard } from './ModerationSectionCard'

interface DuplicateContentSectionProps {
  communityId: string
  duplicates: DuplicateContent[]
}

export function DuplicateContentSection({ communityId, duplicates }: DuplicateContentSectionProps) {
  const dismiss = useDismissModerationItem(communityId)

  return (
    <ModerationSectionCard
      title="Repeated messages"
      description="A member posting the exact same text repeatedly within the last 24 hours — self-repetition (copy-paste spam), not coordinated posting across members."
    >
      {duplicates.length === 0 ? (
        <EmptyState
          icon={Copy}
          title="No repeated messages"
          description="No member has repeated the same message recently."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {duplicates.map((duplicate, index) => (
            <DuplicateContentRow
              key={duplicate.groupMembershipId}
              communityId={communityId}
              duplicate={duplicate}
              index={index}
              dismiss={dismiss}
            />
          ))}
        </ul>
      )}
    </ModerationSectionCard>
  )
}

interface DuplicateContentRowProps {
  communityId: string
  duplicate: DuplicateContent
  index: number
  dismiss: ReturnType<typeof useDismissModerationItem>
}

function DuplicateContentRow({ communityId, duplicate, index, dismiss }: DuplicateContentRowProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const queryClient = useQueryClient()
  const remove = useRemoveGroupMember(duplicate.groupId)

  return (
    <ModerationRow
      index={index}
      isDismissing={isModerationItemDismissing(dismiss, duplicate.groupMembershipId)}
      onDismiss={() => dismiss.mutate({ section: 'duplicate_content', targetId: duplicate.groupMembershipId })}
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
                <DialogTitle>Remove {duplicate.memberDisplayName}?</DialogTitle>
                <DialogDescription>
                  This removes them from &ldquo;{duplicate.groupName}&rdquo; in WhatsApp. This action can&apos;t be
                  undone from here.
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
                    remove.mutate(duplicate.memberId, {
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
        params={{ communityId, groupId: duplicate.groupId }}
        search={{ tab: 'messages' }}
        className={MODERATION_ROW_TRIGGER_CLASS}
      >
        <div className="flex min-w-0 items-center gap-2">
          <Copy className="size-4 shrink-0 text-warning-foreground" />
          <span className="font-medium">{duplicate.memberDisplayName}</span>
          <span className="shrink-0 text-muted-foreground">in {duplicate.groupName}</span>
          <span className="truncate text-muted-foreground">&ldquo;{duplicate.contentPreview}&rdquo;</span>
        </div>
        <span className="shrink-0 text-muted-foreground">{duplicate.occurrenceCount}×</span>
      </Link>
    </ModerationRow>
  )
}
