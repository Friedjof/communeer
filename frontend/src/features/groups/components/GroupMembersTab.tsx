import { ErrorState } from '@/components/feedback/ErrorState'
import { TableSkeleton } from '@/components/feedback/LoadingSkeletons'
import { groupMemberColumns } from '@/features/members/columns'
import { MemberDrawer } from '@/features/members/MemberDrawer'
import { MemberTable } from '@/features/members/MemberTable'
import { useState } from 'react'
import { useGroupMembers } from '../queries'
import type { GroupMemberRow } from '../types'

interface GroupMembersTabProps {
  groupId: string
}

export function GroupMembersTab({ groupId }: GroupMembersTabProps) {
  const members = useGroupMembers(groupId)
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null)

  if (members.isPending) {
    return <TableSkeleton />
  }

  if (members.isError || !members.data) {
    return <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
  }

  const activeMembers = members.data.filter((member) => member.status === 'member')

  return (
    <>
      <MemberTable<GroupMemberRow>
        data={activeMembers}
        columns={groupMemberColumns}
        onRowClick={(row) => setSelectedMemberId(row.memberId)}
        emptyMessage="No members in this group yet."
      />
      <MemberDrawer memberId={selectedMemberId} onOpenChange={(open) => !open && setSelectedMemberId(null)} />
    </>
  )
}
