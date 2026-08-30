import { Link } from '@tanstack/react-router'
import { AlertTriangle, CheckCircle2, UserPlus } from 'lucide-react'
import { CAPACITY_ATTENTION_THRESHOLD } from '@/components/data/CapacityBar'
import { useDismissModerationItem } from '../queries'
import type { CapacityAttention } from '../types'
import { isModerationItemDismissing, MODERATION_ROW_TRIGGER_CLASS, ModerationRow } from './ModerationRow'
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
      description="Groups near their member limit, or with join requests waiting for a decision."
    >
      {groups.length === 0 ? (
        <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 text-primary" />
          Nothing needs attention right now.
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {groups.map((group) => (
            <ModerationRow
              key={group.groupId}
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
          ))}
        </ul>
      )}
    </ModerationSectionCard>
  )
}
