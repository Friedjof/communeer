import { Clock, ShieldCheck, UserPlus } from 'lucide-react'
import { CAPACITY_ATTENTION_THRESHOLD, CapacityBar } from '@/components/data/CapacityBar'
import { ExpandableText } from '@/components/data/ExpandableText'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { StatTile } from '@/features/communities/components/StatTile'
import { formatPercent, formatRelative, initials } from '@/lib/format'
import { useGroupMembers } from '../queries'
import type { GroupDetail } from '../types'
import { ActivityBreakdown } from './ActivityBreakdown'
import { AdminList } from './AdminList'
import { GroupActivityChart } from './GroupActivityChart'
import { GroupHistoryChart } from './GroupHistoryChart'
import { GroupInviteLink } from './GroupInviteLink'

interface GroupOverviewTabProps {
  group: GroupDetail
}

export function GroupOverviewTab({ group }: GroupOverviewTabProps) {
  const members = useGroupMembers(group.id)

  const isNearCapacity =
    Boolean(group.memberLimit) && formatPercent(group.memberCount, group.memberLimit) >= CAPACITY_ATTENTION_THRESHOLD

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start gap-4">
        <Avatar className="size-16 shrink-0">
          {group.pictureUrl ? <AvatarImage src={group.pictureUrl} alt="" /> : null}
          <AvatarFallback className="text-lg">{initials(group.name)}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-medium text-muted-foreground">Description</h2>
          <ExpandableText text={group.description} title={`${group.name} — description`} className="mt-1" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div>
          <h2 className="text-sm font-medium text-muted-foreground">Community</h2>
          <p className="mt-1 font-medium">{group.communityName}</p>
        </div>
        <div>
          <h2 className="text-sm font-medium text-muted-foreground">Type</h2>
          <p className="mt-1">
            {group.isAnnouncementGroup ? <Badge variant="secondary">Announcement group</Badge> : 'Regular group'}
          </p>
        </div>
        <div>
          <h2 className="text-sm font-medium text-muted-foreground">WhatsApp ID</h2>
          <p className="mt-1 font-mono text-xs">{group.waId}</p>
        </div>
        <div>
          <h2 className="text-sm font-medium text-muted-foreground">Invite link</h2>
          <div className="mt-1">
            <GroupInviteLink groupId={group.id} />
          </div>
        </div>
      </div>

      <div className="max-w-sm">
        <div className="mb-2 flex items-center gap-2">
          <h2 className="text-sm font-medium text-muted-foreground">Capacity</h2>
          {isNearCapacity ? <Badge className="bg-destructive text-destructive-foreground">Near capacity</Badge> : null}
        </div>
        <CapacityBar memberCount={group.memberCount} memberLimit={group.memberLimit} />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatTile label="Admins" value={group.adminCount} icon={ShieldCheck} />
        <StatTile
          label="Pending requests"
          value={group.pendingRequestCount}
          icon={UserPlus}
          tone={group.pendingRequestCount > 0 ? 'warning' : 'default'}
        />
        <StatTile
          label="Last activity"
          value={group.lastMessageAt ? formatRelative(group.lastMessageAt) : 'No activity yet'}
          icon={Clock}
        />
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Member growth</h2>
        <GroupHistoryChart communityId={group.communityId} groupId={group.id} />
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Group activity</h2>
        <p className="mb-2 text-xs text-muted-foreground">
          How recently members were last active (message, reaction, or view) — a snapshot, not a trend over time.
        </p>
        {members.isPending ? (
          <ListSkeleton count={3} />
        ) : members.isError || !members.data ? (
          <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
        ) : (
          <div className="animate-in fade-in duration-200">
            <GroupActivityChart members={members.data} />
          </div>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Admins</h2>
          {members.isPending ? (
            <ListSkeleton count={3} />
          ) : members.isError || !members.data ? (
            <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
          ) : (
            <AdminList members={members.data} />
          )}
        </div>
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Activity breakdown</h2>
          {members.isPending ? (
            <ListSkeleton count={3} />
          ) : members.isError || !members.data ? (
            <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
          ) : (
            <ActivityBreakdown members={members.data} />
          )}
        </div>
      </div>
    </div>
  )
}
