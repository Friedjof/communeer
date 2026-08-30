import { useState } from 'react'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { MemberDetailDialog } from '@/features/members/components/MemberDetailDialog'
import { AdminCoverageGapsSection } from './components/AdminCoverageGapsSection'
import { CapacityAttentionSection } from './components/CapacityAttentionSection'
import { JoinBurstsSection } from './components/JoinBurstsSection'
import { ModerationHowItWorks } from './components/ModerationHowItWorks'
import { NeverActiveMembersSection } from './components/NeverActiveMembersSection'
import { useModerationQueue } from './queries'

interface ModerationPageProps {
  communityId: string
}

export function ModerationPage({ communityId }: ModerationPageProps) {
  const queue = useModerationQueue(communityId)
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null)

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Moderation</h1>
        <p className="text-sm text-muted-foreground">
          Flagged groups and members across this community, computed from already-synced data.
        </p>
      </div>

      <ModerationHowItWorks />

      {queue.isPending ? (
        <div className="flex flex-col gap-4">
          <ListSkeleton count={3} />
          <ListSkeleton count={3} />
          <ListSkeleton count={3} />
          <ListSkeleton count={3} />
        </div>
      ) : queue.isError || !queue.data ? (
        <ErrorState message={queue.error?.message} onRetry={() => queue.refetch()} />
      ) : (
        <>
          <AdminCoverageGapsSection communityId={communityId} gaps={queue.data.adminCoverageGaps} />
          <NeverActiveMembersSection
            communityId={communityId}
            members={queue.data.neverActiveMembers}
            onSelectMember={(memberId) => setSelectedMemberId(memberId)}
          />
          <JoinBurstsSection communityId={communityId} bursts={queue.data.joinBursts} />
          <CapacityAttentionSection communityId={communityId} groups={queue.data.capacityAttention} />
        </>
      )}

      <MemberDetailDialog memberId={selectedMemberId} onOpenChange={(open) => !open && setSelectedMemberId(null)} />
    </div>
  )
}
