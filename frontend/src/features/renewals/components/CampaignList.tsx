import { CalendarClock } from 'lucide-react'
import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useRenewalCampaigns } from '../queries'

interface CampaignListProps {
  communityId: string
  selectedCampaignId: string | null
  onSelect: (campaignId: string) => void
}

export function CampaignList({ communityId, selectedCampaignId, onSelect }: CampaignListProps) {
  const campaigns = useRenewalCampaigns(communityId)

  let body: ReactNode
  if (campaigns.isPending) {
    body = <ListSkeleton count={3} />
  } else if (campaigns.isError || !campaigns.data) {
    body = <ErrorState message={campaigns.error?.message} onRetry={() => campaigns.refetch()} />
  } else if (campaigns.data.length === 0) {
    body = (
      <EmptyState
        title="No renewal campaigns yet"
        description="Start one below by selecting members from the suggestion list."
      />
    )
  } else {
    body = (
      <ul className="flex flex-col gap-2">
        {campaigns.data.map((campaign) => (
          <li key={campaign.id}>
            <button
              type="button"
              onClick={() => onSelect(campaign.id)}
              className={cn(
                'flex w-full flex-col gap-2 rounded-lg border p-3 text-left transition-colors hover:bg-muted/60 sm:flex-row sm:items-center sm:justify-between',
                selectedCampaignId === campaign.id && 'border-primary bg-primary/5',
              )}
            >
              <div className="flex items-center gap-2 text-sm">
                <CalendarClock className="size-4 text-muted-foreground" />
                <span>
                  Started {formatDate(campaign.startedAt)} — deadline {formatDate(campaign.deadline)}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="secondary">{campaign.confirmedCount} confirmed</Badge>
                <Badge variant="outline">{campaign.pendingCount} pending</Badge>
                {campaign.expiredCount > 0 ? (
                  <Badge className="bg-warning text-warning-foreground">{campaign.expiredCount} overdue</Badge>
                ) : null}
              </div>
            </button>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Renewal campaigns</CardTitle>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  )
}
