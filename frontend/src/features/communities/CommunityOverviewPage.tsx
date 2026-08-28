import { Link } from '@tanstack/react-router'
import { RefreshCw, ShieldCheck, UserPlus, Users, UsersRound } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { CapacityBar } from '@/components/data/CapacityBar'
import { ExpandableText } from '@/components/data/ExpandableText'
import { ErrorState } from '@/components/feedback/ErrorState'
import { StatTileSkeletons, ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { formatRelative } from '@/lib/format'
import { useCommunityMembers } from '../members/queries'
import { AdminsList } from './components/AdminsList'
import { CommunityGrowthChart } from './components/CommunityGrowthChart'
import { GroupGrowthChart } from './components/GroupGrowthChart'
import { NeedsAttentionList } from './components/NeedsAttentionList'
import { RecentlyJoinedList } from './components/RecentlyJoinedList'
import { StatTile } from './components/StatTile'
import { useCommunity, useCommunityGroups, useSyncCommunity } from './queries'

interface CommunityOverviewPageProps {
  communityId: string
}

export function CommunityOverviewPage({ communityId }: CommunityOverviewPageProps) {
  const community = useCommunity(communityId)
  const groups = useCommunityGroups(communityId)
  const members = useCommunityMembers(communityId)
  const sync = useSyncCommunity(communityId)

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
        <Button onClick={() => sync.mutate()} disabled={sync.isPending} className="gap-1.5">
          <RefreshCw className={sync.isPending ? 'size-4 animate-spin' : 'size-4'} />
          {sync.isPending ? 'Syncing…' : 'Sync now'}
        </Button>
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
            {groupList.map((group) => (
              <Link
                key={group.id}
                to="/c/$communityId/groups/$groupId"
                params={{ communityId, groupId: group.id }}
                search={{ tab: 'overview' }}
                className="flex flex-col gap-2 rounded-lg border p-3 transition-colors hover:bg-muted/60"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{group.name}</span>
                  <div className="flex items-center gap-1.5">
                    {group.isAnnouncementGroup ? <Badge variant="secondary">Announcement</Badge> : null}
                    {group.pendingRequestCount > 0 ? (
                      <Badge className="bg-warning text-warning-foreground">{group.pendingRequestCount} pending</Badge>
                    ) : null}
                  </div>
                </div>
                <CapacityBar memberCount={group.memberCount} memberLimit={group.memberLimit} />
              </Link>
            ))}
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
