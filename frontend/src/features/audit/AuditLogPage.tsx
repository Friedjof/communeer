import { ErrorState } from '@/components/feedback/ErrorState'
import { TableSkeleton } from '@/components/feedback/LoadingSkeletons'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDateTime } from '@/lib/format'
import { useAuditEvents } from './queries'

function actionTone(action: string): 'destructive' | 'secondary' | 'outline' {
  if (action.includes('failed')) return 'destructive'
  if (action.startsWith('auth.')) return 'secondary'
  return 'outline'
}

export function AuditLogPage() {
  const audit = useAuditEvents()

  if (audit.isPending) {
    return <TableSkeleton />
  }

  if (audit.isError || !audit.data) {
    return <ErrorState message={audit.error?.message} onRetry={() => audit.refetch()} />
  }

  const events = [...audit.data].sort(
    (a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime(),
  )

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Audit log</h1>
        <p className="text-sm text-muted-foreground">A reverse-chronological record of admin and sync activity.</p>
      </div>

      {events.length === 0 ? (
        <EmptyState title="No audit events yet" />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((event) => (
                <TableRow key={event.id}>
                  <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                    {formatDateTime(event.occurredAt)}
                  </TableCell>
                  <TableCell>{event.actorUsername ?? <span className="text-muted-foreground">system</span>}</TableCell>
                  <TableCell>
                    <Badge variant={actionTone(event.action)}>{event.action}</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {event.targetType ? `${event.targetType}${event.targetId ? ` · ${event.targetId.slice(0, 8)}` : ''}` : '—'}
                  </TableCell>
                  <TableCell className="max-w-xs truncate font-mono text-xs text-muted-foreground">
                    {event.detail ? JSON.stringify(event.detail) : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
