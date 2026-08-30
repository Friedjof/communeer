import { useState } from 'react'
import type { DataTableExportColumn } from '@/components/data/DataTable'
import { ErrorState } from '@/components/feedback/ErrorState'
import { TableSkeleton } from '@/components/feedback/LoadingSkeletons'
import { useCommunity } from '@/features/communities/queries'
import { formatDate } from '@/lib/format'
import { slugifyFileName } from '@/lib/csv'
import { communityMemberColumns } from './columns'
import { MemberDetailDialog } from './components/MemberDetailDialog'
import { MemberTable } from './MemberTable'
import { useCommunityMembers } from './queries'
import type { CommunityMemberRow } from './types'

interface CommunityMembersPageProps {
  communityId: string
}

function communityMemberRole(row: CommunityMemberRow): string {
  if (row.isCommunityAdmin) return 'Community admin'
  if (row.isAdmin) return 'Group admin'
  return 'Member'
}

const communityMemberExportColumns: DataTableExportColumn<CommunityMemberRow>[] = [
  { header: 'Display Name', value: (row) => row.displayName },
  { header: 'WhatsApp ID', value: (row) => row.waId },
  { header: 'Phone', value: (row) => row.phoneNumberMasked },
  { header: 'Groups', value: (row) => row.groupCount },
  { header: 'Joined', value: (row) => formatDate(row.joinedAt) },
  { header: 'Last Message', value: (row) => formatDate(row.lastMessageAt) },
  { header: 'Role', value: (row) => communityMemberRole(row) },
]

export function CommunityMembersPage({ communityId }: CommunityMembersPageProps) {
  const members = useCommunityMembers(communityId)
  const community = useCommunity(communityId)
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null)

  if (members.isPending) {
    return <TableSkeleton />
  }

  if (members.isError || !members.data) {
    return <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
  }

  const exportFileName = `${slugifyFileName(community.data?.name ?? 'community')}-members.csv`

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
        exportFileName={exportFileName}
        exportColumns={communityMemberExportColumns}
      />
      <MemberDetailDialog memberId={selectedMemberId} onOpenChange={(open) => !open && setSelectedMemberId(null)} />
    </div>
  )
}
