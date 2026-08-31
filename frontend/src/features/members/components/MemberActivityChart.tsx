import { differenceInCalendarDays, parseISO } from 'date-fns'
import { Activity } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { ChartTooltipShell, TruncatingYAxisTick } from '@/components/charts/chart-primitives'
import { formatNumber } from '@/lib/format'
import type { MemberMembership } from '../types'

interface ChartRow {
  groupName: string
  daysAgo: number
}

const Y_AXIS_MAX_LABEL_CHARS = 20

function ActivityTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload as ChartRow | undefined
  if (!row) return null
  return (
    <ChartTooltipShell>
      <p className="font-medium">{row.groupName}</p>
      <p className="text-xs text-muted-foreground">
        Last active {row.daysAgo === 0 ? 'today' : `${formatNumber(row.daysAgo)} day${row.daysAgo === 1 ? '' : 's'} ago`}
      </p>
    </ChartTooltipShell>
  )
}

/**
 * How recently this member was active in each of their groups, as a bar
 * chart — a shorter bar means more recent activity, so this reads at a
 * glance as "which groups is this person most/least engaged with right
 * now". Built from each membership's single `lastActivityAt`: a present-
 * moment snapshot, not a history (there's no per-message log to chart a
 * real trend from — only the latest activity per membership is ever
 * stored), so this is deliberately a recency comparison across groups, not
 * an activity-over-time trend.
 */
export function MemberActivityChart({ memberships }: { memberships: MemberMembership[] }) {
  const rows: ChartRow[] = memberships
    .filter((membership): membership is MemberMembership & { lastActivityAt: string } => membership.lastActivityAt !== null)
    .map((membership) => ({
      groupName: membership.groupName,
      daysAgo: Math.max(0, differenceInCalendarDays(new Date(), parseISO(membership.lastActivityAt))),
    }))
    .sort((a, b) => a.daysAgo - b.daysAgo)

  if (rows.length === 0) {
    return (
      <div className="flex h-[120px] flex-col items-center justify-center gap-1 rounded-lg border border-dashed p-3 text-center">
        <Activity className="size-5 text-muted-foreground" />
        <p className="text-sm font-medium">No activity recorded yet</p>
        <p className="text-xs text-muted-foreground">Nothing posted or observed in any group.</p>
      </div>
    )
  }

  return (
    <div style={{ height: Math.max(120, rows.length * 40) }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
          <CartesianGrid stroke="var(--border)" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
            axisLine={{ stroke: 'var(--border)' }}
            tickLine={false}
            tickFormatter={(value: number) => `${value}d`}
            allowDecimals={false}
          />
          <YAxis
            type="category"
            dataKey="groupName"
            width={140}
            tick={<TruncatingYAxisTick maxChars={Y_AXIS_MAX_LABEL_CHARS} />}
            axisLine={false}
            tickLine={false}
            interval={0}
          />
          <Tooltip content={ActivityTooltip} cursor={{ fill: 'var(--muted)', opacity: 0.5 }} />
          <Bar dataKey="daysAgo" fill="var(--primary)" radius={[0, 4, 4, 0]} isAnimationActive animationDuration={500} maxBarSize={24} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
