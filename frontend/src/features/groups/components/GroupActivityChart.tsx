import { differenceInCalendarDays, parseISO } from 'date-fns'
import { Activity } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { ChartTooltipShell } from '@/components/charts/chart-primitives'
import { EmptyState } from '@/components/feedback/EmptyState'
import { formatNumber } from '@/lib/format'
import type { GroupMemberRow } from '../types'

type RecencyBucket = 'today' | 'week' | 'month' | 'older' | 'never'

const BUCKET_ORDER: RecencyBucket[] = ['today', 'week', 'month', 'older', 'never']

const BUCKET_LABEL: Record<RecencyBucket, string> = {
  today: 'Today',
  week: 'This week',
  month: 'This month',
  older: 'Older',
  never: 'Never active',
}

function bucketFor(lastActivityAt: string | null): RecencyBucket {
  if (!lastActivityAt) return 'never'
  const days = differenceInCalendarDays(new Date(), parseISO(lastActivityAt))
  if (days <= 0) return 'today'
  if (days <= 6) return 'week'
  if (days <= 29) return 'month'
  return 'older'
}

interface ChartRow {
  bucket: RecencyBucket
  label: string
  count: number
}

function ActivityTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload as ChartRow | undefined
  if (!row) return null
  return (
    <ChartTooltipShell>
      <p className="font-medium">{row.label}</p>
      <p className="text-xs text-muted-foreground">
        {formatNumber(row.count)} member{row.count === 1 ? '' : 's'}
      </p>
    </ChartTooltipShell>
  )
}

/**
 * How active this group is, at a glance: members bucketed by how recently
 * `lastActivityAt` fell (today / this week / this month / older / never),
 * as a bar chart. Deliberately a recency distribution rather than a
 * message/reaction/view type split (see `ActivityBreakdown` for that) —
 * this is the more direct answer to "how active is this group".
 *
 * Built entirely from each member's *last* recorded activity — there's no
 * activity log/history to draw a real time series from (by design, only
 * the latest event per member is ever stored), so this is a present-moment
 * snapshot, not a trend over time.
 */
export function GroupActivityChart({ members }: { members: GroupMemberRow[] }) {
  const activeMembers = members.filter((member) => member.status === 'member')

  if (activeMembers.length === 0) {
    return <EmptyState icon={Activity} title="No members yet" description="Activity data appears once this group has members." />
  }

  const counts: Record<RecencyBucket, number> = { today: 0, week: 0, month: 0, older: 0, never: 0 }
  for (const member of activeMembers) {
    counts[bucketFor(member.lastActivityAt)] += 1
  }

  const chartData: ChartRow[] = BUCKET_ORDER.map((bucket) => ({
    bucket,
    label: BUCKET_LABEL[bucket],
    count: counts[bucket],
  }))

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
            axisLine={{ stroke: 'var(--border)' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={40}
            tickFormatter={(value: number) => formatNumber(value)}
            allowDecimals={false}
          />
          <Tooltip content={ActivityTooltip} cursor={{ fill: 'var(--muted)', opacity: 0.5 }} />
          <Bar dataKey="count" fill="var(--primary)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
