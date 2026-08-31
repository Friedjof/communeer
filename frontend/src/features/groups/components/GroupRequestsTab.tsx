import { Check, X } from 'lucide-react'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { HelpTooltip } from '@/components/ui/help-tooltip'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useSession } from '@/features/auth/queries'
import { formatDate, initials } from '@/lib/format'
import { useApproveJoinRequest, useGroupRequests, useRejectJoinRequest } from '../queries'

interface GroupRequestsTabProps {
  groupId: string
}

export function GroupRequestsTab({ groupId }: GroupRequestsTabProps) {
  const requests = useGroupRequests(groupId)
  const approve = useApproveJoinRequest(groupId)
  const reject = useRejectJoinRequest(groupId)
  const session = useSession()
  const canManage = session.data?.role === 'owner' || session.data?.role === 'admin'

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
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {requests.data.map((request, index) => {
            const isBusy =
              (approve.isPending && approve.variables === request.memberId) ||
              (reject.isPending && reject.variables === request.memberId)
            return (
              <TableRow
                key={request.memberId}
                className="animate-in fade-in slide-in-from-bottom-1 duration-200"
                style={{ animationDelay: `${Math.min(index, 15) * 30}ms`, animationFillMode: 'backwards' }}
              >
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
                <TableCell className="text-right">
                  {canManage ? (
                    <div className="flex justify-end gap-1">
                      <HelpTooltip content="Approve this join request">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label="Approve"
                          disabled={isBusy}
                          onClick={() => approve.mutate(request.memberId)}
                        >
                          <Check className="size-4" />
                        </Button>
                      </HelpTooltip>
                      <HelpTooltip content="Reject this join request">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label="Reject"
                          disabled={isBusy}
                          onClick={() => reject.mutate(request.memberId)}
                        >
                          <X className="size-4" />
                        </Button>
                      </HelpTooltip>
                    </div>
                  ) : (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="text-xs text-muted-foreground">—</span>
                      </TooltipTrigger>
                      <TooltipContent>Your role doesn't have access to this</TooltipContent>
                    </Tooltip>
                  )}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
