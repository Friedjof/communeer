import { formatDate, formatDateTime, formatNumber } from '@/lib/format'
import { SnapshotTimeSeriesChart } from '@/components/charts/chart-primitives'
import { useCommunityHistory } from '../queries'

interface CommunityGrowthChartProps {
  communityId: string
}

/** Line chart of a community's total member count over time, one point per
 * sync. Real history depends entirely on sync frequency (see backend
 * `CommunityMemberSnapshot`) — a community synced only a few times will show
 * a short or single-point history rather than a smooth trend. */
export function CommunityGrowthChart({ communityId }: CommunityGrowthChartProps) {
  const history = useCommunityHistory(communityId)

  return (
    <SnapshotTimeSeriesChart
      points={history.data ?? []}
      isPending={history.isPending}
      isError={history.isError || !history.data}
      errorMessage={history.error?.message}
      gradientId="community-growth-fill"
      emptyTitle="No history yet"
      emptyDescription="Growth history is recorded on every sync — run a sync to start tracking this community."
      singlePointNote="Only one sync recorded so far — a growth line appears once this community has synced again."
      renderTooltip={(point) => (
        <>
          <p className="font-medium tabular-nums">{formatNumber(point.memberCount)} members</p>
          <p className="text-xs text-muted-foreground">{formatDateTime(point.recordedAt)}</p>
        </>
      )}
      renderFooter={(latest) => (
        <>
          {formatNumber(latest.memberCount)} members · {formatDate(latest.recordedAt)}
        </>
      )}
    />
  )
}
