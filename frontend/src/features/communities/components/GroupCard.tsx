import { Link } from '@tanstack/react-router'
import { ShieldCheck, TrendingDown, TrendingUp } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { CapacityBar } from '@/components/data/CapacityBar'
import { formatNumber, formatRelative, initials } from '@/lib/format'
import type { GroupSummary } from '../../groups/types'

interface GroupCardProps {
  communityId: string
  group: GroupSummary
  /** Delta between the group's two most-recent recorded snapshots — `undefined`
   * when there isn't enough history yet to compute a trend. */
  recentGrowth: number | undefined
}

export function GroupCard({ communityId, group, recentGrowth }: GroupCardProps) {
  return (
    <Link
      to="/c/$communityId/groups/$groupId"
      params={{ communityId, groupId: group.id }}
      search={{ tab: 'overview' }}
      className="flex flex-col gap-2 rounded-lg border p-3 transition-colors hover:bg-muted/60"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <Avatar className="size-9 shrink-0">
            {group.pictureUrl ? <AvatarImage src={group.pictureUrl} alt="" /> : null}
            <AvatarFallback className="text-xs">{initials(group.name)}</AvatarFallback>
          </Avatar>
          <div className="flex min-w-0 flex-col">
            <span className="truncate font-medium">{group.name}</span>
            {group.description ? (
              <span className="truncate text-xs text-muted-foreground">{group.description}</span>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {group.isAnnouncementGroup ? <Badge variant="secondary">Announcement</Badge> : null}
          {group.pendingRequestCount > 0 ? (
            <Badge className="bg-warning text-warning-foreground">{group.pendingRequestCount} pending</Badge>
          ) : null}
        </div>
      </div>

      <CapacityBar memberCount={group.memberCount} memberLimit={group.memberLimit} />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <ShieldCheck className="size-3.5" />
          {formatNumber(group.adminCount)} {group.adminCount === 1 ? 'admin' : 'admins'}
        </span>
        <span>{group.lastMessageAt ? formatRelative(group.lastMessageAt) : 'No activity yet'}</span>
        {recentGrowth !== undefined && recentGrowth !== 0 ? (
          <span
            className={
              recentGrowth > 0
                ? 'inline-flex items-center gap-0.5 text-success'
                : 'inline-flex items-center gap-0.5 text-destructive'
            }
          >
            {recentGrowth > 0 ? <TrendingUp className="size-3.5" /> : <TrendingDown className="size-3.5" />}
            {recentGrowth > 0 ? '+' : ''}
            {formatNumber(recentGrowth)} recently
          </span>
        ) : null}
      </div>
    </Link>
  )
}
