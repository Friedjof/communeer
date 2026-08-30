import { format, parseISO } from 'date-fns'
import { useState } from 'react'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { formatRelative, initials } from '@/lib/format'
import type { CommunityMemberRow } from '../../members/types'

const RECENT_WINDOW_DAYS = 7
const CHART_WINDOW_DAYS = 14
const DAY_MS = 24 * 60 * 60 * 1000
const MAX_ROWS = 3

interface RecentlyJoinedListProps {
  members: CommunityMemberRow[]
}

interface DayBucket {
  bucketEnd: string
  count: number
}

/** Rolling 24h buckets ending exactly at `now`, most recent bucket last —
 * matches the same window definition as the "last N days" headline number
 * above the chart, so the two never disagree about what "recent" means. This
 * intentionally replaces calendar-week bucketing, which drew the current,
 * still-incomplete week as a full-size bar. */
function buildDailyBuckets(joinDates: Date[], now: Date): DayBucket[] {
  const nowMs = now.getTime()
  const buckets: DayBucket[] = []

  for (let i = CHART_WINDOW_DAYS - 1; i >= 0; i--) {
    const bucketEnd = nowMs - i * DAY_MS
    const bucketStart = bucketEnd - DAY_MS
    const count = joinDates.filter((date) => {
      const time = date.getTime()
      return time > bucketStart && time <= bucketEnd
    }).length
    buckets.push({ bucketEnd: new Date(bucketEnd).toISOString(), count })
  }

  return buckets
}

function JoinsTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  const bucket = payload[0]?.payload as DayBucket | undefined
  if (!bucket) return null
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium tabular-nums">
        {bucket.count} join{bucket.count === 1 ? '' : 's'}
      </p>
      <p className="text-xs text-muted-foreground">{format(parseISO(bucket.bucketEnd), 'MMM d')}</p>
    </div>
  )
}

/** Joins-per-week bar chart plus a short "most recent" detail list. Real
 * WhatsApp data only has a join date from the point Communeer first observed
 * the membership (see sync/service.py) — so this fills in over time rather
 * than reflecting true historical join dates for members seen on the very
 * first sync. */
export function RecentlyJoinedList({ members }: RecentlyJoinedListProps) {
  const withJoinDate = members
    .filter((member): member is CommunityMemberRow & { joinedAt: string } => member.joinedAt !== null)
    .sort((a, b) => b.joinedAt.localeCompare(a.joinedAt))

  // Lazy-initialized once per mount rather than read directly during render
  // (an impure `Date.now()` call on every render is flagged by the linter,
  // and the cutoff only needs to be roughly-now anyway).
  const [now] = useState(() => new Date())
  const recentCutoff = now.getTime() - RECENT_WINDOW_DAYS * 24 * 60 * 60 * 1000
  const newInWindow = withJoinDate.filter((member) => new Date(member.joinedAt).getTime() >= recentCutoff)

  if (withJoinDate.length === 0) {
    return <p className="text-sm text-muted-foreground">No join dates recorded yet.</p>
  }

  const buckets = buildDailyBuckets(
    withJoinDate.map((member) => parseISO(member.joinedAt)),
    now,
  )

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{newInWindow.length}</span> new member
          {newInWindow.length === 1 ? '' : 's'} in the last {RECENT_WINDOW_DAYS} days
        </p>
        <div className="mt-2 h-24 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={buckets} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barCategoryGap="20%">
              <XAxis
                dataKey="bucketEnd"
                tickFormatter={(value: string) => format(parseISO(value), 'MMM d')}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                axisLine={{ stroke: 'var(--border)' }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <Tooltip content={JoinsTooltip} cursor={{ fill: 'var(--muted)', opacity: 0.4 }} />
              <Bar dataKey="count" fill="var(--primary)" radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <ul className="flex flex-col gap-2">
        {withJoinDate.slice(0, MAX_ROWS).map((member) => (
          <li key={member.id} className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm">
            <div className="flex items-center gap-2.5">
              <Avatar className="size-8">
                {member.avatarUrl ? <AvatarImage src={member.avatarUrl} alt="" /> : null}
                <AvatarFallback className="text-xs">{initials(member.displayName)}</AvatarFallback>
              </Avatar>
              <span className="font-medium leading-tight">{member.displayName}</span>
            </div>
            <span className="text-muted-foreground">{formatRelative(member.joinedAt)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
