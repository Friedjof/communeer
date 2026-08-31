import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDateTime } from '@/lib/format'
import type { AuditEvent } from '../types'

const MAX_STAGGERED_ROWS = 15

function actionTone(action: string): 'destructive' | 'secondary' | 'outline' {
  if (action.includes('failed')) return 'destructive'
  if (action.startsWith('auth.')) return 'secondary'
  return 'outline'
}

export function AuditTable({ events: rawEvents }: { events: AuditEvent[] }) {
  const events = [...rawEvents].sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime())

  return (
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
          {events.map((event, index) => (
            <TableRow
              key={event.id}
              className="animate-in fade-in slide-in-from-bottom-1 duration-200"
              style={
                index < MAX_STAGGERED_ROWS
                  ? { animationDelay: `${index * 30}ms`, animationFillMode: 'backwards' }
                  : undefined
              }
            >
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
  )
}
