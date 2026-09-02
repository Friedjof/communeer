import { useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { AlertTriangle, Check, CheckCircle2, UserPlus, X } from 'lucide-react'
import { CAPACITY_ATTENTION_THRESHOLD } from '@/components/data/CapacityBar'
import { Button } from '@/components/ui/button'
import { HelpTooltip } from '@/components/ui/help-tooltip'
import { useApproveJoinRequest, useRejectJoinRequest } from '@/features/groups/queries'
import type { GroupJoinRequest } from '@/features/groups/types'
import { moderationKeys, useDismissModerationItem } from '../queries'
import type { CapacityAttention } from '../types'
import { isModerationItemDismissing, MODERATION_ROW_TRIGGER_CLASS } from './moderationRowHelpers'
import { ModerationRow } from './ModerationRow'
import { ModerationSectionCard } from './ModerationSectionCard'

interface CapacityAttentionSectionProps {
  communityId: string
  groups: CapacityAttention[]
}

export function CapacityAttentionSection({ communityId, groups }: CapacityAttentionSectionProps) {
  const dismiss = useDismissModerationItem(communityId)

  return (
    <ModerationSectionCard
      title="Capacity & pending requests"
      description="Groups near their member limit, or with join requests waiting for a decision — approve or reject requests directly here."
    >
      {groups.length === 0 ? (
        <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 text-primary" />
          Nothing needs attention right now.
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {groups.map((group, index) => (
            <li key={group.groupId} className="flex flex-col gap-1.5">
              <ModerationRow
                index={index}
                isDismissing={isModerationItemDismissing(dismiss, group.groupId)}
                onDismiss={() => dismiss.mutate({ section: 'capacity_attention', targetId: group.groupId })}
              >
                <Link
                  to="/c/$communityId/groups/$groupId"
                  params={{ communityId, groupId: group.groupId }}
                  search={{ tab: group.reason === 'capacity' ? 'overview' : 'requests' }}
                  className={MODERATION_ROW_TRIGGER_CLASS}
                >
                  <div className="flex items-center gap-2">
                    {group.reason === 'requests' ? (
                      <UserPlus className="size-4 shrink-0 text-warning-foreground" />
                    ) : (
                      <AlertTriangle className="size-4 shrink-0 text-destructive" />
                    )}
                    <span className="font-medium">{group.groupName}</span>
                  </div>
                  <span className="flex items-center gap-2 text-muted-foreground">
                    {group.percentFull !== null && group.percentFull >= CAPACITY_ATTENTION_THRESHOLD ? (
                      <span>{group.percentFull}% full</span>
                    ) : null}
                    {group.pendingRequestCount > 0 ? (
                      <span>
                        {group.pendingRequestCount} pending request{group.pendingRequestCount === 1 ? '' : 's'}
                      </span>
                    ) : null}
                  </span>
                </Link>
              </ModerationRow>

              {group.pendingRequests.length > 0 ? (
                <ul className="ml-6 flex flex-col gap-1.5 border-l pl-3">
                  {group.pendingRequests.map((request) => (
                    <PendingRequestRow
                      key={request.memberId}
                      communityId={communityId}
                      groupId={group.groupId}
                      request={request}
                    />
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </ModerationSectionCard>
  )
}

interface PendingRequestRowProps {
  communityId: string
  groupId: string
  request: GroupJoinRequest
}

function PendingRequestRow({ communityId, groupId, request }: PendingRequestRowProps) {
  const queryClient = useQueryClient()
  const approve = useApproveJoinRequest(groupId)
  const reject = useRejectJoinRequest(groupId)
  const isBusy = approve.isPending || reject.isPending

  function invalidateModerationQueue() {
    void queryClient.invalidateQueries({ queryKey: moderationKeys.queue(communityId) })
  }

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border p-2 text-sm">
      <span className="truncate">{request.displayName}</span>
      <div className="flex shrink-0 gap-1">
        <HelpTooltip content="Approve this join request">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Approve"
            disabled={isBusy}
            onClick={() => approve.mutate(request.memberId, { onSuccess: invalidateModerationQueue })}
          >
            <Check className="size-4" />
          </Button>
        </HelpTooltip>
        <HelpTooltip content="Reject this join request">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Reject"
            disabled={isBusy}
            onClick={() => reject.mutate(request.memberId, { onSuccess: invalidateModerationQueue })}
          >
            <X className="size-4" />
          </Button>
        </HelpTooltip>
      </div>
    </li>
  )
}
