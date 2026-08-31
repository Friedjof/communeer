import { RefreshCw, Sparkles, UserX } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { HelpTooltip } from '@/components/ui/help-tooltip'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { useSession } from '@/features/auth/queries'
import { formatDate } from '@/lib/format'
import { useCheckRenewalReactions, useProcessDueRemovals, useRenewalCampaign } from '../queries'
import { ConfirmationsTable } from './ConfirmationsTable'
import { NonRespondersTab } from './NonRespondersTab'

interface CampaignDetailProps {
  campaignId: string
}

export function CampaignDetail({ campaignId }: CampaignDetailProps) {
  const campaign = useRenewalCampaign(campaignId)
  const checkReactions = useCheckRenewalReactions(campaignId)
  const processRemovals = useProcessDueRemovals(campaignId)
  const session = useSession()
  const isViewer = session.data?.role === 'viewer'

  if (campaign.isPending) {
    return <ListSkeleton count={4} />
  }
  if (campaign.isError || !campaign.data) {
    return <ErrorState message={campaign.error?.message} onRetry={() => campaign.refetch()} />
  }

  const data = campaign.data

  return (
    <Card className="animate-in fade-in duration-200">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          Campaign started {formatDate(data.startedAt)} — deadline {formatDate(data.deadline)}
          <Badge variant="secondary" className="gap-1">
            <Sparkles className="size-3" />
            Automated
          </Badge>
        </CardTitle>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary">{data.confirmedCount} confirmed</Badge>
          <Badge variant="outline">{data.pendingCount} pending</Badge>
          {data.expiredCount > 0 ? (
            <Badge className="bg-warning text-warning-foreground">{data.expiredCount} overdue</Badge>
          ) : null}
          {isViewer ? (
            <>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button variant="outline" size="sm" className="gap-1.5" disabled>
                      <RefreshCw className="size-3.5" />
                      Check reactions
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>Your role doesn't have access to this</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button variant="outline" size="sm" className="gap-1.5" disabled>
                      <UserX className="size-3.5" />
                      Process removals
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>Your role doesn't have access to this</TooltipContent>
              </Tooltip>
            </>
          ) : (
            <>
              <HelpTooltip content="Ask WhatsApp for the latest reactions right now">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  disabled={checkReactions.isPending}
                  onClick={() => checkReactions.mutate()}
                >
                  <RefreshCw className={checkReactions.isPending ? 'size-3.5 animate-spin' : 'size-3.5'} />
                  {checkReactions.isPending ? 'Checking…' : 'Check reactions'}
                </Button>
              </HelpTooltip>
              <HelpTooltip content="Remove everyone who declined or missed the deadline from this group">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  disabled={processRemovals.isPending}
                  onClick={() => processRemovals.mutate()}
                >
                  <UserX className="size-3.5" />
                  {processRemovals.isPending ? 'Removing…' : 'Process removals'}
                </Button>
              </HelpTooltip>
            </>
          )}
        </div>
      </CardHeader>
      {checkReactions.error ? (
        <p role="alert" className="px-6 text-sm text-destructive">
          {checkReactions.error.message}
        </p>
      ) : null}
      {processRemovals.error ? (
        <p role="alert" className="px-6 text-sm text-destructive">
          {processRemovals.error.message}
        </p>
      ) : null}
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
