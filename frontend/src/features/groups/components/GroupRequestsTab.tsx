import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDate, initials } from '@/lib/format'
import { useGroupRequests } from '../queries'

interface GroupRequestsTabProps {
  groupId: string
}

export function GroupRequestsTab({ groupId }: GroupRequestsTabProps) {
  const requests = useGroupRequests(groupId)

  if (requests.isPending) {
    return <ListSkeleton count={4} />
  }

  if (requests.isError || !requests.data) {
    return <ErrorState message={requests.error?.message} onRetry={() => requests.refetch()} />
  }

  if (requests.data.length === 0) {
    return <EmptyState title="No pending requests" description="There are no join requests waiting for review." />
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Requester</TableHead>
            <TableHead>WhatsApp ID</TableHead>
            <TableHead>Requested</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {requests.data.map((request) => (
            <TableRow key={request.memberId}>
              <TableCell>
                <div className="flex items-center gap-2.5">
                  <Avatar className="size-8">
                    <AvatarFallback className="text-xs">{initials(request.displayName)}</AvatarFallback>
                  </Avatar>
                  <span className="font-medium">{request.displayName}</span>
                </div>
              </TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">{request.waId}</TableCell>
              <TableCell>{formatDate(request.requestedAt)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
