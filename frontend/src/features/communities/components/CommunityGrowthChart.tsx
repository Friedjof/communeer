import { TrendingUp } from 'lucide-react'
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate, formatDateTime, formatNumber } from '@/lib/format'
import type { CommunityHistoryPoint } from '../types'
import { useCommunityHistory } from '../queries'

interface CommunityGrowthChartProps {
  communityId: string
}

function GrowthTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  const point = payload[0]?.payload as CommunityHistoryPoint | undefined
  if (!point) return null
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium tabular-nums">{formatNumber(point.memberCount)} members</p>
      <p className="text-xs text-muted-foreground">{formatDateTime(point.recordedAt)}</p>
    </div>
  )
}

/** Line chart of a community's total member count over time, one point per
 * sync. Real history depends entirely on sync frequency (see backend
 * `CommunityMemberSnapshot`) — a community synced only a few times will show
 * a short or single-point history rather than a smooth trend. */
export function CommunityGrowthChart({ communityId }: CommunityGrowthChartProps) {
  const history = useCommunityHistory(communityId)

  if (history.isPending) {
    return <Skeleton className="h-64 w-full rounded-lg" />
  }

  if (history.isError || !history.data) {
    return (
      <EmptyState
        icon={TrendingUp}
        title="Couldn't load growth history"
        description={history.error?.message ?? 'Please try again.'}
      />
    )
  }

  const points = history.data

  if (points.length === 0) {
    return (
      <EmptyState
        icon={TrendingUp}
        title="No history yet"
        description="Growth history is recorded on every sync — run a sync to start tracking this community."
      />
    )
  }

  if (points.length === 1) {
    const only = points[0]!
    return (
      <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed p-8 text-center">
        <p className="text-3xl font-semibold tabular-nums">{formatNumber(only.memberCount)}</p>
        <p className="text-sm text-muted-foreground">members as of {formatDate(only.recordedAt)}</p>
        <p className="mt-3 max-w-xs text-xs text-muted-foreground">
          Only one sync recorded so far — a growth line appears once this community has synced again.
        </p>
      </div>
    )
  }

  const latest = points[points.length - 1]!

  return (
    <div className="flex flex-col gap-1">
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="community-growth-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.1} />
                <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="recordedAt"
              tickFormatter={(value: string) => formatDate(value)}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
              axisLine={{ stroke: 'var(--border)' }}
              tickLine={false}
              minTickGap={24}
            />
            <YAxis
              tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={44}
              tickFormatter={(value: number) => formatNumber(value)}
              domain={['auto', 'auto']}
              allowDecimals={false}
            />
            <Tooltip content={GrowthTooltip} cursor={{ stroke: 'var(--muted-foreground)', strokeWidth: 1 }} />
            <Area
              type="monotone"
              dataKey="memberCount"
              stroke="none"
              fill="url(#community-growth-fill)"
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="memberCount"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={{ r: 4, fill: 'var(--primary)', stroke: 'var(--card)', strokeWidth: 2 }}
              activeDot={{ r: 5, fill: 'var(--primary)', stroke: 'var(--card)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-right text-xs text-muted-foreground">
        {formatNumber(latest.memberCount)} members · {formatDate(latest.recordedAt)}
      </p>
    </div>
  )
}
