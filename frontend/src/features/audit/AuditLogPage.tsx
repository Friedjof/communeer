import { useState } from 'react'
import { ErrorState } from '@/components/feedback/ErrorState'
import { TableSkeleton } from '@/components/feedback/LoadingSkeletons'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AuditTable } from './components/AuditTable'
import { useAuditEvents } from './queries'

const ACTION_OPTIONS = [
  'auth.login',
  'auth.login_failed',
  'auth.logout',
  'community.sync',
  'renewal.started',
  'renewal.confirmed',
]

const TARGET_TYPE_OPTIONS = ['user', 'community', 'member']

export function AuditLogPage() {
  const [action, setAction] = useState<string | undefined>(undefined)
  const [targetType, setTargetType] = useState<string | undefined>(undefined)
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')

  const audit = useAuditEvents({
    action,
    targetType,
    since: since ? new Date(since).toISOString() : undefined,
    until: until ? new Date(until).toISOString() : undefined,
  })

  const hasFilters = Boolean(action || targetType || since || until)

  function clearFilters() {
    setAction(undefined)
    setTargetType(undefined)
    setSince('')
    setUntil('')
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Audit log</h1>
        <p className="text-sm text-muted-foreground">A reverse-chronological record of admin and sync activity.</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Action</span>
          <Select value={action ?? 'all'} onValueChange={(value) => setAction(value === 'all' ? undefined : value)}>
            <SelectTrigger className="w-44" aria-label="Filter by action">
              <SelectValue placeholder="All actions" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All actions</SelectItem>
              {ACTION_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Target type</span>
          <Select
            value={targetType ?? 'all'}
            onValueChange={(value) => setTargetType(value === 'all' ? undefined : value)}
          >
            <SelectTrigger className="w-40" aria-label="Filter by target type">
              <SelectValue placeholder="All targets" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All targets</SelectItem>
              {TARGET_TYPE_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Since</span>
          <Input type="date" value={since} onChange={(event) => setSince(event.target.value)} className="w-40" />
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Until</span>
          <Input type="date" value={until} onChange={(event) => setUntil(event.target.value)} className="w-40" />
        </div>

        {hasFilters ? (
          <button
            type="button"
            onClick={clearFilters}
            className="mb-0.5 text-sm text-muted-foreground underline-offset-4 transition-colors hover:underline"
          >
            Clear filters
          </button>
        ) : null}
      </div>

      {audit.isPending ? (
        <TableSkeleton />
      ) : audit.isError || !audit.data ? (
        <ErrorState message={audit.error?.message} onRetry={() => audit.refetch()} />
      ) : audit.data.length === 0 ? (
        <EmptyState
          title={hasFilters ? 'No events match these filters' : 'No audit events yet'}
          description={hasFilters ? 'Try widening the date range or clearing a filter.' : undefined}
        />
      ) : (
        <div className="animate-in fade-in duration-200">
          <AuditTable events={audit.data} />
        </div>
      )}
    </div>
  )
}
