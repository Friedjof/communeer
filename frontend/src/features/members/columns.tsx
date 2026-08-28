import { legacyCreateColumnHelper as createColumnHelper } from '@tanstack/react-table/legacy'
import { ShieldCheck } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { formatDate, initials } from '@/lib/format'
import type { GroupMemberRow } from '../groups/types'
import { MaskedPhone } from './MaskedPhone'
import type { CommunityMemberRow } from './types'

function IdentityCell({ avatarUrl, displayName, waId }: { avatarUrl: string | null; displayName: string; waId: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <Avatar className="size-8">
        {avatarUrl ? <AvatarImage src={avatarUrl} alt="" /> : null}
        <AvatarFallback className="text-xs">{initials(displayName)}</AvatarFallback>
      </Avatar>
      <div className="flex flex-col">
        <span className="font-medium leading-tight">{displayName}</span>
        <span className="text-xs text-muted-foreground leading-tight">{waId}</span>
      </div>
    </div>
  )
}

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

export const groupMemberColumns = [
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
  groupColumnHelper.accessor('isSuperAdmin', {
    header: 'Role',
    cell: (info) => {
      const row = info.row.original
      if (row.isSuperAdmin) return <Badge>Super admin</Badge>
      if (row.isAdmin) return <Badge variant="secondary">Admin</Badge>
      return <span className="text-muted-foreground">Member</span>
    },
  }),
]
