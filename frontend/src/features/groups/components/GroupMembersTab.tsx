import type { DataTableExportColumn } from '@/components/data/DataTable'
import { ErrorState } from '@/components/feedback/ErrorState'
import { TableSkeleton } from '@/components/feedback/LoadingSkeletons'
import { groupMemberColumns } from '@/features/members/columns'
import { MemberDetailDialog } from '@/features/members/components/MemberDetailDialog'
import { MemberTable } from '@/features/members/MemberTable'
import { formatDate } from '@/lib/format'
import { slugifyFileName } from '@/lib/csv'
import { useState } from 'react'
import { useGroup, useGroupMembers } from '../queries'
import type { GroupMemberRow } from '../types'

interface GroupMembersTabProps {
  groupId: string
}

function groupMemberRole(row: GroupMemberRow): string {
  if (row.isSuperAdmin) return 'Super admin'
  if (row.isAdmin) return 'Admin'
  return 'Member'
}

const groupMemberExportColumns: DataTableExportColumn<GroupMemberRow>[] = [
  { header: 'Display Name', value: (row) => row.displayName },
  { header: 'WhatsApp ID', value: (row) => row.waId },
  { header: 'Status', value: (row) => row.status },
  { header: 'Joined', value: (row) => formatDate(row.joinedAt) },
  { header: 'Last Message', value: (row) => formatDate(row.lastMessageAt) },
  { header: 'Role', value: (row) => groupMemberRole(row) },
]

export function GroupMembersTab({ groupId }: GroupMembersTabProps) {
  const members = useGroupMembers(groupId)
  const group = useGroup(groupId)
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null)

  if (members.isPending) {
    return <TableSkeleton />
  }

  if (members.isError || !members.data) {
    return <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
  }

  const activeMembers = members.data.filter((member) => member.status === 'member')
  const exportFileName = `${slugifyFileName(group.data?.name ?? 'group')}-members.csv`

  return (
    <>
      <MemberTable<GroupMemberRow>
        data={activeMembers}
        columns={groupMemberColumns(groupId)}
        onRowClick={(row) => setSelectedMemberId(row.memberId)}
        emptyMessage="No members in this group yet."
        exportFileName={exportFileName}
        exportColumns={groupMemberExportColumns}
      />
      <MemberDetailDialog memberId={selectedMemberId} onOpenChange={(open) => !open && setSelectedMemberId(null)} />
    </>
  )
}
