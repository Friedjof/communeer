import { cn } from '@/lib/utils'
import { formatNumber, formatPercent } from '@/lib/format'

interface CapacityBarProps {
  memberCount: number
  memberLimit: number | null
  className?: string
  showLabel?: boolean
}

/** Threshold used everywhere a group is flagged as "needs attention". */
export const CAPACITY_ATTENTION_THRESHOLD = 90

export function CapacityBar({ memberCount, memberLimit, className, showLabel = true }: CapacityBarProps) {
  if (!memberLimit) {
    return (
      <div className={cn('flex items-center justify-between gap-2 text-sm', className)}>
        {showLabel ? <span className="text-muted-foreground">{formatNumber(memberCount)} members</span> : null}
        <span className="text-xs text-muted-foreground">No limit</span>
      </div>
    )
  }

  const percent = formatPercent(memberCount, memberLimit)
  const barColor =
    percent >= CAPACITY_ATTENTION_THRESHOLD ? 'bg-destructive' : percent >= 75 ? 'bg-warning' : 'bg-primary'

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      {showLabel ? (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            {formatNumber(memberCount)} / {formatNumber(memberLimit)}
          </span>
          <span className="font-medium tabular-nums">{percent}%</span>
        </div>
      ) : null}
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full transition-all', barColor)}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
    </div>
  )
}
