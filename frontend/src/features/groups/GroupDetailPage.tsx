import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { GroupAdvancedTab } from './components/GroupAdvancedTab'
import { GroupMembersTab } from './components/GroupMembersTab'
import { GroupOverviewTab } from './components/GroupOverviewTab'
import { GroupRequestsTab } from './components/GroupRequestsTab'
import { useGroup } from './queries'
import type { GroupDetailTab } from './types'

interface GroupDetailPageProps {
  groupId: string
  tab: GroupDetailTab
  onTabChange: (tab: GroupDetailTab) => void
}

export function GroupDetailPage({ groupId, tab, onTabChange }: GroupDetailPageProps) {
  const group = useGroup(groupId)

  if (group.isPending) {
    return <ListSkeleton count={6} />
  }

  if (group.isError || !group.data) {
    return <ErrorState message={group.error?.message} onRetry={() => group.refetch()} />
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold">{group.data.name}</h1>
        {group.data.isAnnouncementGroup ? <Badge variant="secondary">Announcement</Badge> : null}
      </div>

      <Tabs value={tab} onValueChange={(value) => onTabChange(value as GroupDetailTab)}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="members">Members</TabsTrigger>
          <TabsTrigger value="requests">
            Requests
            {group.data.pendingRequestCount > 0 ? (
              <Badge className="ml-1 h-4 bg-warning px-1 text-[10px] text-warning-foreground">
                {group.data.pendingRequestCount}
              </Badge>
            ) : null}
          </TabsTrigger>
          <TabsTrigger value="advanced">Advanced</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <GroupOverviewTab group={group.data} />
        </TabsContent>
        <TabsContent value="members">
          <GroupMembersTab groupId={groupId} />
        </TabsContent>
        <TabsContent value="requests">
          <GroupRequestsTab groupId={groupId} />
        </TabsContent>
        <TabsContent value="advanced">
          <GroupAdvancedTab groupId={groupId} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
