import type { DataTableExportColumn } from '@/components/data/DataTable'
import { ErrorState } from '@/components/feedback/ErrorState'
import { TableSkeleton } from '@/components/feedback/LoadingSkeletons'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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

type RoleFilter = 'all' | 'super-admin' | 'admin' | 'member'

const ROLE_FILTER_LABELS: Record<RoleFilter, string> = {
  all: 'All roles',
  'super-admin': 'Super admin',
  admin: 'Admin',
  member: 'Member',
}

function matchesRoleFilter(row: GroupMemberRow, filter: RoleFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'super-admin') return row.isSuperAdmin
  if (filter === 'admin') return row.isAdmin && !row.isSuperAdmin
  return !row.isAdmin && !row.isSuperAdmin
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
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all')

  if (members.isPending) {
    return <TableSkeleton />
  }

  if (members.isError || !members.data) {
    return <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
  }

  const activeMembers = members.data
    .filter((member) => member.status === 'member')
    .filter((member) => matchesRoleFilter(member, roleFilter))
  const exportFileName = `${slugifyFileName(group.data?.name ?? 'group')}-members.csv`

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Role</span>
          <Select value={roleFilter} onValueChange={(value) => setRoleFilter(value as RoleFilter)}>
            <SelectTrigger className="w-40" aria-label="Filter by role">
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

      <MemberTable<GroupMemberRow>
        data={activeMembers}
        columns={groupMemberColumns(groupId)}
        onRowClick={(row) => setSelectedMemberId(row.memberId)}
        emptyMessage={roleFilter === 'all' ? 'No members in this group yet.' : 'No members match this filter.'}
        exportFileName={exportFileName}
        exportColumns={groupMemberExportColumns}
      />
      <MemberDetailDialog memberId={selectedMemberId} onOpenChange={(open) => !open && setSelectedMemberId(null)} />
    </>
  )
}
