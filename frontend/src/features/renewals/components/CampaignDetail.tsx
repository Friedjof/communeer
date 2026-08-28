import { AlertTriangle, CheckCircle2, Clock } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { formatDate, initials } from '@/lib/format'
import { useConfirmRenewal, useNonResponders, useRenewalCampaign } from '../queries'
import type { RenewalConfirmation } from '../types'

interface CampaignDetailProps {
  campaignId: string
}

function StatusCell({ confirmation }: { confirmation: RenewalConfirmation }) {
  if (confirmation.status === 'confirmed') {
    return (
      <Badge variant="secondary" className="gap-1">
        <CheckCircle2 className="size-3" />
        Confirmed
      </Badge>
    )
  }
  if (confirmation.isExpired) {
    return (
      <Badge className="gap-1 bg-warning text-warning-foreground">
        <AlertTriangle className="size-3" />
        Pending — overdue
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1 text-muted-foreground">
      <Clock className="size-3" />
      Pending
    </Badge>
  )
}

function MemberIdentity({ displayName, waId }: { displayName: string; waId: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <Avatar className="size-8">
        <AvatarFallback className="text-xs">{initials(displayName)}</AvatarFallback>
      </Avatar>
      <div className="flex flex-col">
        <span className="font-medium leading-tight">{displayName}</span>
        <span className="text-xs text-muted-foreground leading-tight">{waId}</span>
      </div>
    </div>
  )
}

function ConfirmationsTable({ campaignId, confirmations }: { campaignId: string; confirmations: RenewalConfirmation[] }) {
  const confirmRenewal = useConfirmRenewal(campaignId)

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
            <TableHead>Responded</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {confirmations.map((confirmation) => (
            <TableRow key={confirmation.memberId}>
              <TableCell>
                <MemberIdentity displayName={confirmation.displayName} waId={confirmation.waId} />
              </TableCell>
              <TableCell>
                <StatusCell confirmation={confirmation} />
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">{formatDate(confirmation.respondedAt)}</TableCell>
              <TableCell className="text-right">
                {confirmation.status === 'pending' ? (
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
                ) : null}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function NonRespondersTab({ campaignId }: { campaignId: string }) {
  const nonResponders = useNonResponders(campaignId)

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
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-foreground" />
        <p>
          These members missed the deadline without confirming. Removal is <strong>manual</strong> — review each
          person, confirm in WhatsApp, then remove them there yourself. There is no remove button here by design.
        </p>
      </div>
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Member</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {nonResponders.data.map((confirmation) => (
              <TableRow key={confirmation.memberId}>
                <TableCell>
                  <MemberIdentity displayName={confirmation.displayName} waId={confirmation.waId} />
                </TableCell>
                <TableCell>
                  <StatusCell confirmation={confirmation} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

export function CampaignDetail({ campaignId }: CampaignDetailProps) {
  const campaign = useRenewalCampaign(campaignId)

  if (campaign.isPending) {
    return <ListSkeleton count={4} />
  }
  if (campaign.isError || !campaign.data) {
    return <ErrorState message={campaign.error?.message} onRetry={() => campaign.refetch()} />
  }

  const data = campaign.data

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">
          Campaign started {formatDate(data.startedAt)} — deadline {formatDate(data.deadline)}
        </CardTitle>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary">{data.confirmedCount} confirmed</Badge>
          <Badge variant="outline">{data.pendingCount} pending</Badge>
          {data.expiredCount > 0 ? (
            <Badge className="bg-warning text-warning-foreground">{data.expiredCount} overdue</Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="all">
          <TabsList>
            <TabsTrigger value="all">All confirmations</TabsTrigger>
            <TabsTrigger value="non-responders">
              Not confirmed — review
              {data.expiredCount > 0 ? (
                <Badge className="ml-1 h-4 bg-warning px-1 text-[10px] text-warning-foreground">
                  {data.expiredCount}
                </Badge>
              ) : null}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="all">
            <ConfirmationsTable campaignId={campaignId} confirmations={data.confirmations} />
          </TabsContent>
          <TabsContent value="non-responders">
            <NonRespondersTab campaignId={campaignId} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}
