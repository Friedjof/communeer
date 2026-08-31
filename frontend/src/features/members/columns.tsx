import { legacyCreateColumnHelper as createColumnHelper } from '@tanstack/react-table/legacy'
import { ShieldCheck } from 'lucide-react'
import { ActivityBar } from '@/components/data/ActivityBar'
import { ActivityColumnHeader } from '@/components/data/MessageActivityCell'
import { Badge } from '@/components/ui/badge'
import { formatDate } from '@/lib/format'
import type { GroupMemberRow } from '../groups/types'
import { GroupMemberRowActions } from './components/GroupMemberRowActions'
import { IdentityCell } from './components/IdentityCell'
import { MaskedPhone } from './components/MaskedPhone'
import type { CommunityMemberRow } from './types'

const communityColumnHelper = createColumnHelper<CommunityMemberRow>()

export const communityMemberColumns = [
  communityColumnHelper.accessor('displayName', {
    header: 'Member',
    cell: (info) => (
      <IdentityCell avatarUrl={info.row.original.avatarUrl} displayName={info.getValue()} waId={info.row.original.waId} />
    ),
  }),
  communityColumnHelper.accessor('phoneNumberMasked', {
    header: 'Phone',
    cell: (info) => <MaskedPhone value={info.getValue()} />,
  }),
  communityColumnHelper.accessor('groupCount', {
    header: 'Groups',
    cell: (info) => <span className="tabular-nums">{info.getValue()}</span>,
  }),
  communityColumnHelper.accessor('joinedAt', {
    header: 'Joined',
    cell: (info) => formatDate(info.getValue()),
  }),
  communityColumnHelper.accessor('lastActivityAt', {
    header: ActivityColumnHeader,
    cell: (info) => {
      const row = info.row.original
      return (
        <ActivityBar
          lastActivityType={row.lastActivityType}
          lastActivityAt={row.lastActivityAt}
          lastActivityContent={row.lastActivityContent}
        />
      )
    },
  }),
  communityColumnHelper.accessor('isCommunityAdmin', {
    header: 'Role',
    cell: (info) => {
      const row = info.row.original
      if (row.isCommunityAdmin) {
        return (
          <Badge className="gap-1">
            <ShieldCheck className="size-3" />
            Community admin
          </Badge>
        )
      }
      if (row.isAdmin) return <Badge variant="secondary">Group admin</Badge>
      return <span className="text-muted-foreground">Member</span>
    },
  }),
]

const groupColumnHelper = createColumnHelper<GroupMemberRow>()

/** A factory (not a plain array, unlike `communityMemberColumns`) because
 * the trailing actions column needs to know which group to scope its
 * promote/demote/remove mutations to. */
export function groupMemberColumns(groupId: string) {
  return [
    groupColumnHelper.accessor('displayName', {
    header: 'Member',
    cell: (info) => (
      <IdentityCell avatarUrl={info.row.original.avatarUrl} displayName={info.getValue()} waId={info.row.original.waId} />
    ),
  }),
  groupColumnHelper.accessor('status', {
    header: 'Status',
    cell: (info) => (
      <Badge variant={info.getValue() === 'pending' ? 'secondary' : 'outline'} className="capitalize">
        {info.getValue()}
      </Badge>
    ),
  }),
  groupColumnHelper.accessor('joinedAt', {
    header: 'Joined',
    cell: (info) => new Date(info.getValue()).toLocaleDateString(),
  }),
  groupColumnHelper.accessor('lastActivityAt', {
    header: ActivityColumnHeader,
    cell: (info) => {
      const row = info.row.original
      return (
        <ActivityBar
          lastActivityType={row.lastActivityType}
          lastActivityAt={row.lastActivityAt}
          lastActivityContent={row.lastActivityContent}
        />
      )
    },
  }),
  groupColumnHelper.accessor('isSuperAdmin', {
    header: 'Role',
    cell: (info) => {
      const row = info.row.original
      if (row.isSuperAdmin) return <Badge>Super admin</Badge>
      if (row.isAdmin) return <Badge variant="secondary">Admin</Badge>
      return <span className="text-muted-foreground">Member</span>
    },
  }),
    groupColumnHelper.display({
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: (info) => <GroupMemberRowActions groupId={groupId} member={info.row.original} />,
    }),
  ]
}
