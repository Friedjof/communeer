import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { initials } from '@/lib/format'
import type { GroupMemberRow } from '../types'

/** Every member with admin rights in this group, super admins first. Kept
 * lightweight (name + avatar + role badge) — a supplementary section, not a
 * replacement for the full Members tab. */
export function AdminList({ members }: { members: GroupMemberRow[] }) {
  const admins = members
    .filter((member) => member.status === 'member' && member.isAdmin)
    .sort((a, b) => Number(b.isSuperAdmin) - Number(a.isSuperAdmin) || a.displayName.localeCompare(b.displayName))

  if (admins.length === 0) {
    return <p className="text-sm text-muted-foreground">No admins found.</p>
  }

  return (
    <ul className="flex flex-col gap-2">
      {admins.map((member, index) => (
        <li
          key={member.memberId}
          className="flex animate-in items-center justify-between gap-3 rounded-lg border p-3 text-sm fade-in slide-in-from-bottom-1 duration-200"
          style={{ animationDelay: `${Math.min(index, 8) * 30}ms`, animationFillMode: 'backwards' }}
        >
          <div className="flex min-w-0 items-center gap-2.5">
            <Avatar className="size-8 shrink-0">
              {member.avatarUrl ? <AvatarImage src={member.avatarUrl} alt="" /> : null}
              <AvatarFallback className="text-xs">{initials(member.displayName)}</AvatarFallback>
            </Avatar>
            <span className="truncate font-medium">{member.displayName}</span>
          </div>
          {member.isSuperAdmin ? (
            <Badge className="shrink-0">Super admin</Badge>
          ) : (
            <Badge variant="secondary" className="shrink-0">
              Admin
            </Badge>
          )}
        </li>
      ))}
    </ul>
  )
}
