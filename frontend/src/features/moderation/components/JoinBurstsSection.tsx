import { Link } from '@tanstack/react-router'
import { TrendingUp } from 'lucide-react'
import { EmptyState } from '@/components/feedback/EmptyState'
import { formatPercent } from '@/lib/format'
import { useDismissModerationItem } from '../queries'
import type { JoinBurst } from '../types'
import { isModerationItemDismissing, MODERATION_ROW_TRIGGER_CLASS, ModerationRow } from './ModerationRow'
import { ModerationSectionCard } from './ModerationSectionCard'

interface JoinBurstsSectionProps {
  communityId: string
  bursts: JoinBurst[]
}

export function JoinBurstsSection({ communityId, bursts }: JoinBurstsSectionProps) {
  const dismiss = useDismissModerationItem(communityId)

  return (
    <ModerationSectionCard
      title="Join bursts"
      description="Groups where an unusually large share of current members joined within the last 24 hours — a real flood/spam signal."
    >
      {bursts.length === 0 ? (
        <EmptyState
          icon={TrendingUp}
          title="No join bursts"
          description="No group has an unusual spike of recent joins right now."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {bursts.map((burst) => (
            <ModerationRow
              key={burst.groupId}
              isDismissing={isModerationItemDismissing(dismiss, burst.groupId)}
              onDismiss={() => dismiss.mutate({ section: 'join_bursts', targetId: burst.groupId })}
            >
              <Link
                to="/c/$communityId/groups/$groupId"
                params={{ communityId, groupId: burst.groupId }}
                search={{ tab: 'overview' }}
                className={MODERATION_ROW_TRIGGER_CLASS}
              >
                <div className="flex items-center gap-2">
                  <TrendingUp className="size-4 shrink-0 text-warning-foreground" />
                  <span className="font-medium">{burst.groupName}</span>
                </div>
                <span className="text-muted-foreground">
                  {burst.recentJoinCount} joined in the last 24h ({formatPercent(burst.recentJoinCount, burst.memberCount)}%)
                </span>
              </Link>
            </ModerationRow>
          ))}
        </ul>
      )}
    </ModerationSectionCard>
  )
}
