import { BarChart3 } from 'lucide-react'
import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { ChartTooltipShell, TruncatingYAxisTick } from '@/components/charts/chart-primitives'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate, formatNumber } from '@/lib/format'
import type { GroupHistorySeries } from '../types'
import { useCommunityGroupsHistory } from '../queries'

interface GroupGrowthChartProps {
  communityId: string
}

interface GroupGrowthRow {
  groupId: string
  groupName: string
  growth: number
  currentMemberCount: number
  since: string | null
}

function buildRows(series: GroupHistorySeries[]): GroupGrowthRow[] {
  return series
    .filter((group) => group.snapshots.length > 0)
    .map((group) => {
      const first = group.snapshots[0]!
      const last = group.snapshots[group.snapshots.length - 1]!
      return {
        groupId: group.groupId,
        groupName: group.groupName,
        growth: last.memberCount - first.memberCount,
        currentMemberCount: last.memberCount,
        since: group.snapshots.length > 1 ? first.recordedAt : null,
      }
    })
    .sort((a, b) => b.growth - a.growth || b.currentMemberCount - a.currentMemberCount)
}

const Y_AXIS_MAX_LABEL_CHARS = 16

interface GrowthBarShapeProps {
  x?: number
  y?: number
  width?: number
  height?: number
  payload?: GroupGrowthRow
}

/** Custom bar renderer so a group with exactly zero growth still shows a
 * visible mark (a small centered square on the zero baseline) instead of a
 * literal zero-width/invisible bar — the flat/no-change state must read as
 * "nothing changed here", not as "this row is broken". */
function GrowthBarShape(props: GrowthBarShapeProps) {
  const { x = 0, y = 0, width = 0, height = 0, payload } = props
  const growth = payload?.growth ?? 0
  const color = growth > 0 ? 'var(--success)' : growth < 0 ? 'var(--destructive)' : 'var(--muted-foreground)'

  if (growth === 0) {
    const size = Math.min(10, height)
    const cy = y + height / 2
    return <rect x={x - size / 2} y={cy - size / 2} width={size} height={size} rx={2} fill={color} />
  }

  return <rect x={x} y={y} width={width} height={height} rx={3} fill={color} />
}

function GrowthTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload as GroupGrowthRow | undefined
  if (!row) return null
  const sign = row.growth > 0 ? '+' : ''
  return (
    <ChartTooltipShell>
      <p className="font-medium">{row.groupName}</p>
      <p className="tabular-nums">
        {sign}
        {formatNumber(row.growth)} members
        {row.since ? ` since ${formatDate(row.since)}` : ' (only one sync recorded)'}
      </p>
      <p className="text-xs text-muted-foreground">{formatNumber(row.currentMemberCount)} members now</p>
    </ChartTooltipShell>
  )
}

/** Horizontal diverging bar chart: which groups are growing vs shrinking,
 * comparing each group's first vs. most recent recorded snapshot. Growth
 * resolution is only as fine as sync frequency — a group synced only once
 * shows zero growth by definition, not a broken state. */
export function GroupGrowthChart({ communityId }: GroupGrowthChartProps) {
  const groupsHistory = useCommunityGroupsHistory(communityId)

  if (groupsHistory.isPending) {
    return <Skeleton className="h-64 w-full rounded-lg" />
  }

  if (groupsHistory.isError || !groupsHistory.data) {
    return (
      <EmptyState
        icon={BarChart3}
        title="Couldn't load group history"
        description={groupsHistory.error?.message ?? 'Please try again.'}
      />
    )
  }

  const rows = buildRows(groupsHistory.data)

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No group history yet"
        description="Group growth is recorded on every sync — run a sync to start tracking these groups."
      />
    )
  }

  const noGroupHasTwoSyncsYet = rows.every((row) => row.since === null)
  const allFlat = rows.every((row) => row.growth === 0)
  const maxAbsGrowth = Math.max(1, ...rows.map((row) => Math.abs(row.growth)))
  const chartHeight = Math.max(160, rows.length * 36 + 24)

  return (
    <div className="flex flex-col gap-2">
      <div style={{ height: chartHeight }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ top: 4, right: 20, left: 0, bottom: 4 }}
            barCategoryGap="28%"
          >
            <XAxis
              type="number"
              domain={[-maxAbsGrowth, maxAbsGrowth]}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <YAxis
              type="category"
              dataKey="groupName"
              width={130}
              tick={<TruncatingYAxisTick maxChars={Y_AXIS_MAX_LABEL_CHARS} />}
              axisLine={false}
              tickLine={false}
              interval={0}
            />
            <ReferenceLine x={0} stroke="var(--border)" />
            <Tooltip content={GrowthTooltip} cursor={{ fill: 'var(--muted)', opacity: 0.4 }} />
            <Bar dataKey="growth" maxBarSize={20} isAnimationActive={false} shape={GrowthBarShape} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {noGroupHasTwoSyncsYet ? (
        <p className="text-xs text-muted-foreground">
          Growth shows once a group has been synced at least twice — right now every group has only one recorded
          snapshot.
        </p>
      ) : allFlat ? (
        <p className="text-xs text-muted-foreground">
          No group has grown or shrunk since its earliest recorded snapshot yet.
        </p>
      ) : null}
    </div>
  )
}
