import { Line } from 'recharts'
import { SnapshotTimeSeriesChart } from '@/components/charts/chart-primitives'
import { formatDate, formatDateTime, formatNumber } from '@/lib/format'
import { useCommunityGroupsHistory } from '../../communities/queries'

interface GroupHistoryChartProps {
  communityId: string
  groupId: string
}

/**
 * This group's member-count-over-time (plus a thin pending-requests line),
 * one point per sync. There's no per-group history endpoint — the
 * community-wide `useCommunityGroupsHistory` already returns every group's
 * series in one call, so this just filters that result down to `groupId`
 * client-side rather than adding a new backend endpoint.
 *
 * Shares its sparse-data handling (0 / 1 / 2+ snapshots) and time-based
 * `XAxis` with `CommunityGrowthChart` via `SnapshotTimeSeriesChart` — this
 * chart's only differences are the data source, the extra pending-requests
 * line, and the tooltip/footer text.
 */
export function GroupHistoryChart({ communityId, groupId }: GroupHistoryChartProps) {
  const groupsHistory = useCommunityGroupsHistory(communityId)
  const points = groupsHistory.data?.find((series) => series.groupId === groupId)?.snapshots ?? []

  return (
    <SnapshotTimeSeriesChart
      points={points}
      isPending={groupsHistory.isPending}
      isError={groupsHistory.isError || !groupsHistory.data}
      errorMessage={groupsHistory.error?.message}
      gradientId="group-history-fill"
      emptyTitle="No history yet"
      emptyDescription="Growth history is recorded on every sync — run a sync to start tracking this group."
      singlePointNote="Only one sync recorded so far — a growth line appears once this group has synced again."
      renderTooltip={(point) => (
        <>
          <p className="font-medium tabular-nums">{formatNumber(point.memberCount)} members</p>
          <p className="text-xs text-muted-foreground">
            {formatNumber(point.pendingRequestCount)} pending request{point.pendingRequestCount === 1 ? '' : 's'}
          </p>
          <p className="text-xs text-muted-foreground">{formatDateTime(point.recordedAt)}</p>
        </>
      )}
      renderFooter={(latest) => (
        <>
          {formatNumber(latest.memberCount)} members · {formatNumber(latest.pendingRequestCount)} pending ·{' '}
          {formatDate(latest.recordedAt)}
        </>
      )}
      extraLines={
        <Line
          type="monotone"
          dataKey="pendingRequestCount"
          stroke="var(--warning)"
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      }
    />
  )
}
