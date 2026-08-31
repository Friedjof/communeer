import { TrendingUp } from 'lucide-react'
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { TooltipContentProps } from 'recharts'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate, formatNumber } from '@/lib/format'

/**
 * Shared visual shell for every chart's custom tooltip content — the same
 * `"rounded-lg border bg-popover px-3 py-2 text-sm shadow-md"` box was
 * repeated identically across all chart components. Callers still own the
 * tooltip's actual content (labels, values); this only wraps it.
 */
export function ChartTooltipShell({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border bg-popover px-3 py-2 text-sm shadow-md">{children}</div>
}

/** Truncates by Unicode code point (not UTF-16 code unit), so an emoji at
 * the cut point doesn't get split into a broken half-glyph — real group
 * names here often start with one (e.g. "🔒Unity α | Residents Only"). */
function truncateLabel(name: string, maxCodePoints: number): string {
  const chars = [...name]
  if (chars.length <= maxCodePoints) return name
  return `${chars.slice(0, maxCodePoints - 1).join('').trimEnd()}…`
}

const DEFAULT_Y_AXIS_MAX_LABEL_CHARS = 18

interface TruncatingYAxisTickProps {
  x?: number
  y?: number
  payload?: { value: string }
  maxChars?: number
}

/** Recharts' default category-axis tick wraps long labels across multiple
 * lines within the fixed axis width, which collides with a fixed per-row
 * bar height — real WhatsApp group/member names are frequently much longer
 * than the axis has room for. Renders a single truncated line with an
 * ellipsis instead; the full name is still available via the row's own
 * tooltip on hover. Pass as `tick={<TruncatingYAxisTick maxChars={16} />}` —
 * Recharts clones the element with its own `x`/`y`/`payload` at render
 * time. */
export function TruncatingYAxisTick({
  x = 0,
  y = 0,
  payload,
  maxChars = DEFAULT_Y_AXIS_MAX_LABEL_CHARS,
}: TruncatingYAxisTickProps) {
  if (!payload) return null
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fontSize={12} fill="var(--muted-foreground)">
      {truncateLabel(payload.value, maxChars)}
    </text>
  )
}

export interface SnapshotPoint {
  recordedAt: string
  memberCount: number
}

export interface SnapshotTimeSeriesChartProps<T extends SnapshotPoint> {
  /** Full snapshot series, oldest first. */
  points: T[]
  isPending: boolean
  isError: boolean
  errorMessage?: string
  /** Must be unique per chart instance on the page — used as the SVG gradient id. */
  gradientId: string
  emptyTitle: string
  emptyDescription: string
  /** Shown under the single-point card, e.g. "...a growth line appears once this community has synced again." */
  singlePointNote: string
  /** Tooltip body for one point — wrapped in `ChartTooltipShell` automatically. */
  renderTooltip: (point: T) => ReactNode
  /** Footer line under the chart, e.g. "123 members · Aug 1, 2026". */
  renderFooter: (latest: T) => ReactNode
  /** Extra `<Line>`/`<Area>` elements rendered after the default member-count line
   * (e.g. `GroupHistoryChart`'s pending-request-count line). */
  extraLines?: ReactNode
  icon?: LucideIcon
}

/**
 * Sparse-data-aware line/area chart for a member-count-over-time snapshot
 * series: an empty state (no snapshots), a static single-value card (one
 * snapshot — a trend line would be misleading), or the full time-scaled
 * chart (two or more). Shared by `CommunityGrowthChart` and
 * `GroupHistoryChart`, which differ only in their data source, tooltip
 * content, and whether they render an extra pending-requests line.
 */
export function SnapshotTimeSeriesChart<T extends SnapshotPoint>({
  points,
  isPending,
  isError,
  errorMessage,
  gradientId,
  emptyTitle,
  emptyDescription,
  singlePointNote,
  renderTooltip,
  renderFooter,
  extraLines,
  icon = TrendingUp,
}: SnapshotTimeSeriesChartProps<T>) {
  if (isPending) {
    return <Skeleton className="h-64 w-full rounded-lg" />
  }

  if (isError) {
    return (
      <EmptyState icon={icon} title="Couldn't load growth history" description={errorMessage ?? 'Please try again.'} />
    )
  }

  if (points.length === 0) {
    return <EmptyState icon={icon} title={emptyTitle} description={emptyDescription} />
  }

  if (points.length === 1) {
    const only = points[0]!
    return (
      <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed p-8 text-center">
        <p className="text-3xl font-semibold tabular-nums">{formatNumber(only.memberCount)}</p>
        <p className="text-sm text-muted-foreground">members as of {formatDate(only.recordedAt)}</p>
        <p className="mt-3 max-w-xs text-xs text-muted-foreground">{singlePointNote}</p>
      </div>
    )
  }

  const latest = points[points.length - 1]!

  // Recharts' category axis (the implicit default when `type`/`scale` are
  // unset) spreads points evenly regardless of real elapsed time, so two
  // syncs an hour apart and a third three weeks later would render as
  // equidistant. Converting `recordedAt` to a numeric timestamp and using a
  // `type="number" scale="time"` axis instead positions each point
  // proportional to when it actually happened.
  const chartData = points.map((point) => ({ ...point, recordedAtMs: new Date(point.recordedAt).getTime() }))

  function GrowthTooltip({ active, payload }: TooltipContentProps) {
    if (!active || !payload?.length) return null
    const point = payload[0]?.payload as T | undefined
    if (!point) return null
    return <ChartTooltipShell>{renderTooltip(point)}</ChartTooltipShell>
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.1} />
                <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="recordedAtMs"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(value: number) => formatDate(new Date(value))}
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
              fill={`url(#${gradientId})`}
              isAnimationActive animationDuration={500}
            />
            <Line
              type="monotone"
              dataKey="memberCount"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={{ r: 4, fill: 'var(--primary)', stroke: 'var(--card)', strokeWidth: 2 }}
              activeDot={{ r: 5, fill: 'var(--primary)', stroke: 'var(--card)', strokeWidth: 2 }}
              isAnimationActive animationDuration={500}
            />
            {extraLines}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-right text-xs text-muted-foreground">{renderFooter(latest)}</p>
    </div>
  )
}
