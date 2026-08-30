import { Link } from '@tanstack/react-router'
import { ShieldAlert } from 'lucide-react'
import { EmptyState } from '@/components/feedback/EmptyState'
import { useDismissModerationItem } from '../queries'
import type { AdminCoverageGap } from '../types'
import { isModerationItemDismissing, MODERATION_ROW_TRIGGER_CLASS, ModerationRow } from './ModerationRow'
import { ModerationSectionCard } from './ModerationSectionCard'

interface AdminCoverageGapsSectionProps {
  communityId: string
  gaps: AdminCoverageGap[]
}

export function AdminCoverageGapsSection({ communityId, gaps }: AdminCoverageGapsSectionProps) {
  const dismiss = useDismissModerationItem(communityId)

  return (
    <ModerationSectionCard
      title="Admin coverage gaps"
      description="Groups with one admin or none — a single point of failure if that person leaves or is removed."
    >
      {gaps.length === 0 ? (
        <EmptyState
          icon={ShieldAlert}
          title="Every group has admin coverage"
          description="No group currently relies on a single admin."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {gaps.map((gap) => (
            <ModerationRow
              key={gap.groupId}
              isDismissing={isModerationItemDismissing(dismiss, gap.groupId)}
              onDismiss={() => dismiss.mutate({ section: 'admin_coverage_gaps', targetId: gap.groupId })}
            >
              <Link
                to="/c/$communityId/groups/$groupId"
                params={{ communityId, groupId: gap.groupId }}
                search={{ tab: 'overview' }}
                className={MODERATION_ROW_TRIGGER_CLASS}
              >
                <div className="flex items-center gap-2">
                  <ShieldAlert className="size-4 shrink-0 text-destructive" />
                  <span className="font-medium">{gap.groupName}</span>
                </div>
                <span className="text-muted-foreground">
                  {gap.adminCount} admin{gap.adminCount === 1 ? '' : 's'}
                </span>
              </Link>
            </ModerationRow>
          ))}
        </ul>
      )}
    </ModerationSectionCard>
  )
}
