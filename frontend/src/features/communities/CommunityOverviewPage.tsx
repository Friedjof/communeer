import { Link } from '@tanstack/react-router'
import {
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  UserPlus,
  Users,
  UsersRound,
} from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { CapacityBar } from '@/components/data/CapacityBar'
import { ExpandableText } from '@/components/data/ExpandableText'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { StatTileSkeletons, ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { formatNumber, formatRelative, initials } from '@/lib/format'
import { useSession } from '@/features/auth/queries'
import { useCommunityMembers } from '../members/queries'
import type { GroupHistorySeries } from './types'
import { AdminsList } from './components/AdminsList'
import { CommunityGrowthChart } from './components/CommunityGrowthChart'
import { GroupGrowthChart } from './components/GroupGrowthChart'
import { NeedsAttentionList } from './components/NeedsAttentionList'
import { RecentlyJoinedList } from './components/RecentlyJoinedList'
import { StatTile } from './components/StatTile'
import { useCommunity, useCommunityGroups, useCommunityGroupsHistory, useSyncCommunity } from './queries'

/** Delta between a group's two most-recent recorded snapshots — `null` when
 * fewer than two snapshots exist yet (growth isn't meaningful from a single
 * data point). Mirrors the "first vs. last" comparison `GroupGrowthChart`
 * already does, just narrowed to the last two points for a per-row trend. */
function buildRecentGrowthByGroupId(series: GroupHistorySeries[] | undefined): Map<string, number> {
  const growthByGroupId = new Map<string, number>()
  if (!series) return growthByGroupId
  for (const group of series) {
    if (group.snapshots.length < 2) continue
    const last = group.snapshots[group.snapshots.length - 1]!
    const secondLast = group.snapshots[group.snapshots.length - 2]!
    growthByGroupId.set(group.groupId, last.memberCount - secondLast.memberCount)
  }
  return growthByGroupId
}

interface CommunityOverviewPageProps {
  communityId: string
}

export function CommunityOverviewPage({ communityId }: CommunityOverviewPageProps) {
  const community = useCommunity(communityId)
  const groups = useCommunityGroups(communityId)
  const members = useCommunityMembers(communityId)
  const groupsHistory = useCommunityGroupsHistory(communityId)
  const sync = useSyncCommunity(communityId)
  const session = useSession()
  const isViewer = session.data?.role === 'viewer'

  if (community.isPending || groups.isPending || members.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <StatTileSkeletons />
        <ListSkeleton count={4} />
      </div>
    )
  }

  if (community.isError || !community.data) {
    return <ErrorState message={community.error?.message} onRetry={() => community.refetch()} />
  }

  if (groups.isError || !groups.data) {
    return <ErrorState message={groups.error?.message} onRetry={() => groups.refetch()} />
  }

  if (members.isError || !members.data) {
    return <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
  }

  const data = community.data
  const groupList = groups.data
  const memberList = members.data
  const recentGrowthByGroupId = buildRecentGrowthByGroupId(groupsHistory.data)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{data.name}</h1>
          <ExpandableText
            text={data.description}
            title={`${data.name} — description`}
            maxLength={160}
            className="max-w-xl text-sm text-muted-foreground"
          />
          <p className="mt-1 text-xs text-muted-foreground">Last synced {formatRelative(data.lastSyncedAt)}</p>
        </div>
        {isViewer ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button disabled className="gap-1.5">
                  <RefreshCw className="size-4" />
                  Sync now
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>Your role doesn't have access to this</TooltipContent>
          </Tooltip>
        ) : (
          <Button onClick={() => sync.mutate()} disabled={sync.isPending} className="gap-1.5">
            <RefreshCw className={sync.isPending ? 'size-4 animate-spin' : 'size-4'} />
            {sync.isPending ? 'Syncing…' : 'Sync now'}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Members" value={data.memberCount} icon={Users} />
        <StatTile label="Groups" value={data.groupCount} icon={UsersRound} />
        <StatTile label="Admins" value={data.adminCount} icon={ShieldCheck} />
        <StatTile
          label="Pending requests"
          value={data.pendingRequestCount}
          icon={UserPlus}
          tone={data.pendingRequestCount > 0 ? 'warning' : 'default'}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Community growth</CardTitle>
          </CardHeader>
          <CardContent>
            <CommunityGrowthChart communityId={communityId} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Group growth</CardTitle>
          </CardHeader>
          <CardContent>
            <GroupGrowthChart communityId={communityId} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Groups</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {groupList.length === 0 ? (
              <EmptyState icon={UsersRound} title="No groups yet" description="Groups appear here once this community has synced." />
            ) : null}
            {groupList.map((group) => {
              const recentGrowth = recentGrowthByGroupId.get(group.id)
              return (
                <Link
                  key={group.id}
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
                        {recentGrowth > 0 ? (
                          <TrendingUp className="size-3.5" />
                        ) : (
                          <TrendingDown className="size-3.5" />
                        )}
                        {recentGrowth > 0 ? '+' : ''}
                        {formatNumber(recentGrowth)} recently
                      </span>
                    ) : null}
                  </div>
                </Link>
              )
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Needs attention</CardTitle>
          </CardHeader>
          <CardContent>
            <NeedsAttentionList communityId={communityId} groups={groupList} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Admins</CardTitle>
          </CardHeader>
          <CardContent>
            <AdminsList members={memberList} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recently joined</CardTitle>
          </CardHeader>
          <CardContent>
            <RecentlyJoinedList members={memberList} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
