import { Link } from '@tanstack/react-router'
import { AlertTriangle, CheckCircle2, UserPlus } from 'lucide-react'
import { CAPACITY_ATTENTION_THRESHOLD } from '@/components/data/CapacityBar'
import { formatPercent } from '@/lib/format'
import type { GroupSummary } from '../../groups/types'

interface NeedsAttentionListProps {
  communityId: string
  groups: GroupSummary[]
}

interface AttentionItem {
  group: GroupSummary
  reason: 'capacity' | 'requests'
}

export function NeedsAttentionList({ communityId, groups }: NeedsAttentionListProps) {
  const items: AttentionItem[] = []

  for (const group of groups) {
    if (group.memberLimit && formatPercent(group.memberCount, group.memberLimit) >= CAPACITY_ATTENTION_THRESHOLD) {
      items.push({ group, reason: 'capacity' })
    }
    if (group.pendingRequestCount > 0) {
      items.push({ group, reason: 'requests' })
    }
  }

  if (items.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
        <CheckCircle2 className="size-4 text-primary" />
        Nothing needs attention right now.
      </div>
    )
  }

  return (
    <ul className="flex flex-col gap-2">
      {items.map((item) => (
        <li key={`${item.group.id}-${item.reason}`}>
          <Link
            to="/c/$communityId/groups/$groupId"
            params={{ communityId, groupId: item.group.id }}
            search={{ tab: item.reason === 'requests' ? 'requests' : 'overview' }}
            className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm transition-colors hover:bg-muted/60"
          >
            <div className="flex items-center gap-2">
              {item.reason === 'capacity' ? (
                <AlertTriangle className="size-4 shrink-0 text-destructive" />
              ) : (
                <UserPlus className="size-4 shrink-0 text-warning-foreground" />
              )}
              <span className="font-medium">{item.group.name}</span>
            </div>
            <span className="text-muted-foreground">
              {item.reason === 'capacity'
                ? `${formatPercent(item.group.memberCount, item.group.memberLimit)}% full`
                : `${item.group.pendingRequestCount} pending request${item.group.pendingRequestCount === 1 ? '' : 's'}`}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}
