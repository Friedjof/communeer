import { Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { HelpTooltip } from '@/components/ui/help-tooltip'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { EmptyState } from '@/components/feedback/EmptyState'
import { useSession } from '@/features/auth/queries'
import { formatDate, formatRelative } from '@/lib/format'
import { useConfirmRenewal, useSendRenewalReminder } from '../queries'
import type { RenewalConfirmation } from '../types'
import { MemberIdentity } from './MemberIdentity'
import { RemoveFromCampaignButton } from './RemoveFromCampaignButton'
import { StatusCell } from './StatusCell'

const MAX_STAGGERED_ROWS = 15

function ReminderCell({
  confirmation,
  isViewer,
  sendReminder,
}: {
  confirmation: RenewalConfirmation
  isViewer: boolean
  sendReminder: ReturnType<typeof useSendRenewalReminder>
}) {
  if (confirmation.status !== 'pending' || confirmation.declinedAt || confirmation.removedAt) {
    return null
  }

  const isBusy = sendReminder.isPending && sendReminder.variables === confirmation.memberId
  const label = confirmation.reminderSentAt ? `Sent ${formatRelative(confirmation.reminderSentAt)}` : 'Not sent'

  return (
    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
      <span>{label}</span>
      {isViewer ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Button size="icon-sm" variant="ghost" disabled>
                <Send className="size-3.5" />
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>Your role doesn't have access to this</TooltipContent>
        </Tooltip>
      ) : (
        <HelpTooltip content={confirmation.reminderSentAt ? 'Resend the reminder' : 'Send the reminder now'}>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={confirmation.reminderSentAt ? 'Resend reminder' : 'Send reminder'}
            disabled={isBusy}
            onClick={() => sendReminder.mutate(confirmation.memberId)}
          >
            <Send className="size-3.5" />
          </Button>
        </HelpTooltip>
      )}
    </div>
  )
}

export function ConfirmationsTable({ campaignId, confirmations }: { campaignId: string; confirmations: RenewalConfirmation[] }) {
  const confirmRenewal = useConfirmRenewal(campaignId)
  const sendReminder = useSendRenewalReminder(campaignId)
  const session = useSession()
  const isViewer = session.data?.role === 'viewer'

  if (confirmations.length === 0) {
    return <EmptyState title="No members in this campaign" />
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Member</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Reminder</TableHead>
            <TableHead>Responded</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {confirmations.map((confirmation, index) => (
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
              <TableCell>
                <ReminderCell confirmation={confirmation} isViewer={isViewer} sendReminder={sendReminder} />
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">{formatDate(confirmation.respondedAt)}</TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-1">
                  {confirmation.status === 'pending' && !confirmation.removedAt ? (
                    isViewer ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span>
                            <Button size="sm" variant="outline" disabled>
                              Mark confirmed
                            </Button>
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>Your role doesn't have access to this</TooltipContent>
                      </Tooltip>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={confirmRenewal.isPending && confirmRenewal.variables === confirmation.memberId}
                        onClick={() => confirmRenewal.mutate(confirmation.memberId)}
                      >
                        {confirmRenewal.isPending && confirmRenewal.variables === confirmation.memberId
                          ? 'Marking…'
                          : 'Mark confirmed'}
                      </Button>
                    )
                  ) : null}
                  <RemoveFromCampaignButton campaignId={campaignId} confirmation={confirmation} isViewer={isViewer} />
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
