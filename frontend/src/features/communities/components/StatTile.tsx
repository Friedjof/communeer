import type { LucideIcon } from 'lucide-react'
import { formatNumber } from '@/lib/format'

interface StatTileProps {
  label: string
  /** A plain count is formatted with `formatNumber`; pass a pre-formatted
   * string (e.g. a relative time like "3 minutes ago") for non-numeric
   * headline stats. */
  value: number | string
  icon: LucideIcon
  tone?: 'default' | 'warning'
}

export function StatTile({ label, value, icon: Icon, tone = 'default' }: StatTileProps) {
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card p-4">
      <div
        className={
          tone === 'warning'
            ? 'flex size-10 shrink-0 items-center justify-center rounded-full bg-warning/20 text-warning-foreground'
            : 'flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary'
        }
      >
        <Icon className="size-5" />
      </div>
      <div>
        <p className="text-2xl font-semibold tabular-nums leading-none">
          {typeof value === 'number' ? formatNumber(value) : value}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}
