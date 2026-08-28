import { useState } from 'react'
import { ErrorState } from '@/components/feedback/ErrorState'
import { TableSkeleton } from '@/components/feedback/LoadingSkeletons'
import { communityMemberColumns } from './columns'
import { MemberDrawer } from './MemberDrawer'
import { MemberTable } from './MemberTable'
import { useCommunityMembers } from './queries'
import type { CommunityMemberRow } from './types'

interface CommunityMembersPageProps {
  communityId: string
}

export function CommunityMembersPage({ communityId }: CommunityMembersPageProps) {
  const members = useCommunityMembers(communityId)
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null)

  if (members.isPending) {
    return <TableSkeleton />
  }

  if (members.isError || !members.data) {
    return <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Members</h1>
        <p className="text-sm text-muted-foreground">{members.data.length} members across this community.</p>
      </div>
      <MemberTable<CommunityMemberRow>
        data={members.data}
        columns={communityMemberColumns}
        onRowClick={(row) => setSelectedMemberId(row.id)}
      />
      <MemberDrawer memberId={selectedMemberId} onOpenChange={(open) => !open && setSelectedMemberId(null)} />
    </div>
  )
}
