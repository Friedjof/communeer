import { useState } from 'react'
import type { DataTableExportColumn } from '@/components/data/DataTable'
import { ErrorState } from '@/components/feedback/ErrorState'
import { TableSkeleton } from '@/components/feedback/LoadingSkeletons'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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

type RoleFilter = 'all' | 'community-admin' | 'group-admin' | 'member'

const ROLE_FILTER_LABELS: Record<RoleFilter, string> = {
  all: 'All roles',
  'community-admin': 'Community admin',
  'group-admin': 'Group admin',
  member: 'Member',
}

function matchesRoleFilter(row: CommunityMemberRow, filter: RoleFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'community-admin') return row.isCommunityAdmin
  if (filter === 'group-admin') return row.isAdmin && !row.isCommunityAdmin
  return !row.isAdmin && !row.isCommunityAdmin
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
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all')

  if (members.isPending) {
    return <TableSkeleton />
  }

  if (members.isError || !members.data) {
    return <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
  }

  const exportFileName = `${slugifyFileName(community.data?.name ?? 'community')}-members.csv`
  const filteredMembers = members.data.filter((row) => matchesRoleFilter(row, roleFilter))

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Members</h1>
        <p className="text-sm text-muted-foreground">{members.data.length} members across this community.</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Role</span>
          <Select value={roleFilter} onValueChange={(value) => setRoleFilter(value as RoleFilter)}>
            <SelectTrigger className="w-44" aria-label="Filter by role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(ROLE_FILTER_LABELS) as RoleFilter[]).map((option) => (
                <SelectItem key={option} value={option}>
                  {ROLE_FILTER_LABELS[option]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {roleFilter !== 'all' ? (
          <button
            type="button"
            onClick={() => setRoleFilter('all')}
            className="mb-0.5 text-sm text-muted-foreground underline-offset-4 transition-colors hover:underline"
          >
            Clear filters
          </button>
        ) : null}
      </div>

      <MemberTable<CommunityMemberRow>
        data={filteredMembers}
        columns={communityMemberColumns}
        onRowClick={(row) => setSelectedMemberId(row.id)}
        exportFileName={exportFileName}
        exportColumns={communityMemberExportColumns}
        emptyMessage={roleFilter === 'all' ? undefined : 'No members match this filter.'}
      />
      <MemberDetailDialog memberId={selectedMemberId} onOpenChange={(open) => !open && setSelectedMemberId(null)} />
    </div>
  )
}
