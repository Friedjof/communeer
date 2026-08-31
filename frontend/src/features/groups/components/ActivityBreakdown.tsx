import { formatNumber } from '@/lib/format'
import type { GroupMemberRow } from '../types'

type ActivityBucket = 'message' | 'reaction' | 'view' | 'never'

const ACTIVITY_META: Record<ActivityBucket, { label: string; barColor: string; dotColor: string }> = {
  message: { label: 'Messaged', barColor: 'bg-primary', dotColor: 'bg-primary' },
  reaction: { label: 'Reacted only', barColor: 'bg-success', dotColor: 'bg-success' },
  view: { label: 'Viewed only', barColor: 'bg-muted-foreground', dotColor: 'bg-muted-foreground' },
  never: { label: 'Never active', barColor: 'bg-muted', dotColor: 'bg-muted' },
}

const ACTIVITY_ORDER: ActivityBucket[] = ['message', 'reaction', 'view', 'never']

/** Client-side breakdown of `lastActivityType` across this group's active
 * members — a segmented bar plus counts, deliberately simple rather than a
 * new chart type. */
export function ActivityBreakdown({ members }: { members: GroupMemberRow[] }) {
  const activeMembers = members.filter((member) => member.status === 'member')
  const counts: Record<ActivityBucket, number> = { message: 0, reaction: 0, view: 0, never: 0 }
  for (const member of activeMembers) {
    counts[(member.lastActivityType ?? 'never') as ActivityBucket] += 1
  }
  const total = activeMembers.length

  if (total === 0) {
    return <p className="text-sm text-muted-foreground">No members yet.</p>
  }

  return (
    <div className="flex animate-in flex-col gap-3 rounded-lg border p-3 fade-in duration-200">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        {ACTIVITY_ORDER.filter((bucket) => counts[bucket] > 0).map((bucket) => (
          <div
            key={bucket}
            className={ACTIVITY_META[bucket].barColor}
            style={{ width: `${(counts[bucket] / total) * 100}%` }}
          />
        ))}
      </div>
      <ul className="flex flex-col gap-1.5 text-sm">
        {ACTIVITY_ORDER.map((bucket) => (
          <li key={bucket} className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-muted-foreground">
              <span className={`size-2 shrink-0 rounded-full ${ACTIVITY_META[bucket].dotColor}`} />
              {ACTIVITY_META[bucket].label}
            </span>
            <span className="tabular-nums font-medium">{formatNumber(counts[bucket])}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
