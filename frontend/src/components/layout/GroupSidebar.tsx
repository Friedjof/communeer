import { Link } from '@tanstack/react-router'
import { Search } from 'lucide-react'
import { useState } from 'react'
import { CapacityBar } from '@/components/data/CapacityBar'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { useCommunityGroups } from '@/features/communities/queries'
import { cn } from '@/lib/utils'

interface GroupSidebarProps {
  communityId: string
  currentGroupId?: string
  onNavigate?: () => void
  className?: string
}

export function GroupSidebar({ communityId, currentGroupId, onNavigate, className }: GroupSidebarProps) {
  const groups = useCommunityGroups(communityId)
  const [search, setSearch] = useState('')

  const filtered = (groups.data ?? []).filter((group) => group.name.toLowerCase().includes(search.toLowerCase()))

  return (
    <aside className={cn('flex h-full flex-col gap-3 overflow-y-auto border-r bg-card p-3', className)}>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search groups…"
          className="pl-8"
        />
      </div>

      {groups.isPending ? (
        <ListSkeleton count={4} />
      ) : (
        <ul className="flex flex-col gap-1">
          {filtered.map((group) => (
            <li key={group.id}>
              <Link
                to="/c/$communityId/groups/$groupId"
                params={{ communityId, groupId: group.id }}
                search={{ tab: 'overview' }}
                onClick={onNavigate}
                className={cn(
                  'flex flex-col gap-1.5 rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-muted',
                  currentGroupId === group.id && 'bg-primary/10',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">{group.name}</span>
                  {group.pendingRequestCount > 0 ? (
                    <Badge className="h-4 shrink-0 bg-warning px-1 text-[10px] text-warning-foreground">
                      {group.pendingRequestCount}
                    </Badge>
                  ) : null}
                </div>
                <CapacityBar memberCount={group.memberCount} memberLimit={group.memberLimit} showLabel={false} />
              </Link>
            </li>
          ))}
          {filtered.length === 0 ? <p className="px-2.5 py-2 text-sm text-muted-foreground">No groups found.</p> : null}
        </ul>
      )}
    </aside>
  )
}
