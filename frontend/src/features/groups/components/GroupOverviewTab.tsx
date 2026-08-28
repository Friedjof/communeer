import { CapacityBar } from '@/components/data/CapacityBar'
import { ExpandableText } from '@/components/data/ExpandableText'
import { Badge } from '@/components/ui/badge'
import type { GroupDetail } from '../types'

interface GroupOverviewTabProps {
  group: GroupDetail
}

export function GroupOverviewTab({ group }: GroupOverviewTabProps) {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-sm font-medium text-muted-foreground">Description</h2>
        <ExpandableText text={group.description} title={`${group.name} — description`} className="mt-1" />
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
      </div>

      <div className="max-w-sm">
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Capacity</h2>
        <CapacityBar memberCount={group.memberCount} memberLimit={group.memberLimit} />
      </div>
    </div>
  )
}
