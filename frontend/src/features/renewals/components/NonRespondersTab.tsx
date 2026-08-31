import { AlertTriangle } from 'lucide-react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { useSession } from '@/features/auth/queries'
import { useNonResponders } from '../queries'
import { MemberIdentity } from './MemberIdentity'
import { RemoveFromCampaignButton } from './RemoveFromCampaignButton'
import { StatusCell } from './StatusCell'

const MAX_STAGGERED_ROWS = 15

export function NonRespondersTab({ campaignId }: { campaignId: string }) {
  const nonResponders = useNonResponders(campaignId)
  const session = useSession()
  const isViewer = session.data?.role === 'viewer'

  if (nonResponders.isPending) {
    return <ListSkeleton count={3} />
  }
  if (nonResponders.isError || !nonResponders.data) {
    return <ErrorState message={nonResponders.error?.message} onRetry={() => nonResponders.refetch()} />
  }
  if (nonResponders.data.length === 0) {
    return <EmptyState title="Nobody is overdue yet" description="Members show up here once the deadline passes without a confirmation." />
  }

  return (
    <div className="flex animate-in flex-col gap-3 fade-in duration-200">
      <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-foreground" />
        <p>
          These members missed the deadline (or declined via ❌) without confirming. Removing them from the group is{' '}
          <strong>manual</strong> — review each person, then use "Process removals" above once you're ready.
        </p>
      </div>
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Member</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {nonResponders.data.map((confirmation, index) => (
              <TableRow
                key={confirmation.memberId}
                className="animate-in fade-in slide-in-from-bottom-1 duration-200"
                style={
                  index < MAX_STAGGERED_ROWS
                    ? { animationDelay: `${index * 30}ms`, animationFillMode: 'backwards' }
                    : undefined
                }
              >
                <TableCell>
                  <MemberIdentity displayName={confirmation.displayName} waId={confirmation.waId} />
                </TableCell>
                <TableCell>
                  <StatusCell confirmation={confirmation} />
                </TableCell>
                <TableCell className="text-right">
                  <RemoveFromCampaignButton campaignId={campaignId} confirmation={confirmation} isViewer={isViewer} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
