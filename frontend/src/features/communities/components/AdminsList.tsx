import { ShieldCheck } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { initials } from '@/lib/format'
import type { CommunityMemberRow } from '../../members/types'

interface AdminsListProps {
  members: CommunityMemberRow[]
}

/** Everyone with admin rights somewhere in this community — community
 * admins (admin of the announcement group) first, then plain group admins. */
export function AdminsList({ members }: AdminsListProps) {
  const admins = members
    .filter((member) => member.isAdmin)
    .sort((a, b) => Number(b.isCommunityAdmin) - Number(a.isCommunityAdmin) || a.displayName.localeCompare(b.displayName))

  if (admins.length === 0) {
    return <p className="text-sm text-muted-foreground">No admins found.</p>
  }

  return (
    <ul className="flex flex-col gap-2">
      {admins.map((member) => (
        <li key={member.id} className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm">
          <div className="flex items-center gap-2.5">
            <Avatar className="size-8">
              {member.avatarUrl ? <AvatarImage src={member.avatarUrl} alt="" /> : null}
              <AvatarFallback className="text-xs">{initials(member.displayName)}</AvatarFallback>
            </Avatar>
            <div className="flex flex-col">
              <span className="font-medium leading-tight">{member.displayName}</span>
              <span className="text-xs text-muted-foreground leading-tight">
                {member.groupCount} group{member.groupCount === 1 ? '' : 's'}
              </span>
            </div>
          </div>
          {member.isCommunityAdmin ? (
            <Badge className="gap-1">
              <ShieldCheck className="size-3" />
              Community admin
            </Badge>
          ) : (
            <Badge variant="secondary">Group admin</Badge>
          )}
        </li>
      ))}
    </ul>
  )
}
