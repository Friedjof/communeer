import { Archive, ArchiveRestore, CalendarClock, Trash2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { HelpTooltip } from '@/components/ui/help-tooltip'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { useSession } from '@/features/auth/queries'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useArchiveCampaign, useDeleteCampaign, useRenewalCampaigns, useUnarchiveCampaign } from '../queries'
import type { RenewalCampaignSummary } from '../types'

interface CampaignListProps {
  groupId: string
  selectedCampaignId: string | null
  onSelect: (campaignId: string | null) => void
}

function CampaignRow({
  campaign,
  isSelected,
  isViewer,
  onSelect,
  archiveCampaign,
  unarchiveCampaign,
  deleteCampaign,
}: {
  campaign: RenewalCampaignSummary
  isSelected: boolean
  isViewer: boolean
  onSelect: (campaignId: string | null) => void
  archiveCampaign: ReturnType<typeof useArchiveCampaign>
  unarchiveCampaign: ReturnType<typeof useUnarchiveCampaign>
  deleteCampaign: ReturnType<typeof useDeleteCampaign>
}) {
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const isArchived = campaign.archivedAt !== null
  const isBusy =
    (archiveCampaign.isPending && archiveCampaign.variables === campaign.id) ||
    (unarchiveCampaign.isPending && unarchiveCampaign.variables === campaign.id) ||
    (deleteCampaign.isPending && deleteCampaign.variables === campaign.id)

  return (
    <div
      className={cn(
        'flex w-full flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between',
        isSelected && 'border-primary bg-primary/5',
        isArchived && 'opacity-60',
      )}
    >
      <button
        type="button"
        onClick={() => onSelect(campaign.id)}
        className="flex flex-1 flex-col gap-2 text-left transition-colors hover:text-foreground sm:flex-row sm:items-center sm:gap-3"
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
          {isArchived ? <Badge variant="outline">Archived</Badge> : null}
          {campaign.totalCount === 0 ? (
            <span className="text-xs text-muted-foreground italic">No members left</span>
          ) : null}
        </div>
      </button>

      {!isViewer ? (
        <div className="flex items-center gap-1">
          {isArchived ? (
            <HelpTooltip content="Restore this campaign to the default view">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Unarchive"
                disabled={isBusy}
                onClick={() => unarchiveCampaign.mutate(campaign.id)}
              >
                <ArchiveRestore className="size-4" />
              </Button>
            </HelpTooltip>
          ) : (
            <HelpTooltip content="Archive this campaign">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Archive"
                disabled={isBusy}
                onClick={() => archiveCampaign.mutate(campaign.id)}
              >
                <Archive className="size-4" />
              </Button>
            </HelpTooltip>
          )}
          {isArchived ? (
            <HelpTooltip content="Permanently delete this campaign">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Delete"
                disabled={isBusy}
                onClick={() => setConfirmDeleteOpen(true)}
              >
                <Trash2 className="size-4" />
              </Button>
            </HelpTooltip>
          ) : null}
        </div>
      ) : null}

      <Dialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this campaign?</DialogTitle>
            <DialogDescription>
              This permanently deletes the campaign and every member's confirmation in it. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleteCampaign.isPending}
              onClick={() => {
                deleteCampaign.mutate(campaign.id, {
                  onSuccess: () => {
                    setConfirmDeleteOpen(false)
                    if (isSelected) onSelect(null)
                  },
                })
              }}
            >
              {deleteCampaign.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export function CampaignList({ groupId, selectedCampaignId, onSelect }: CampaignListProps) {
  const campaigns = useRenewalCampaigns(groupId)
  const session = useSession()
  const isViewer = session.data?.role === 'viewer'
  const [showArchived, setShowArchived] = useState(false)
  const archiveCampaign = useArchiveCampaign(groupId)
  const unarchiveCampaign = useUnarchiveCampaign(groupId)
  const deleteCampaign = useDeleteCampaign(groupId)

  let body: ReactNode
  if (campaigns.isPending) {
    body = <ListSkeleton count={3} />
  } else if (campaigns.isError || !campaigns.data) {
    body = <ErrorState message={campaigns.error?.message} onRetry={() => campaigns.refetch()} />
  } else {
    const visibleCampaigns = campaigns.data.filter((campaign) => showArchived || campaign.archivedAt === null)
    if (visibleCampaigns.length === 0) {
      body = (
        <EmptyState
          title={campaigns.data.length === 0 ? 'No renewal campaigns yet' : 'No archived campaigns'}
          description={
            campaigns.data.length === 0
              ? 'Start one below by selecting members from the suggestion list.'
              : 'Campaigns you archive will show up here.'
          }
        />
      )
    } else {
      body = (
        <ul className="flex flex-col gap-2">
          {visibleCampaigns.map((campaign, index) => (
            <li
              key={campaign.id}
              className="animate-in fade-in slide-in-from-bottom-1 duration-200"
              style={{ animationDelay: `${Math.min(index, 10) * 30}ms`, animationFillMode: 'backwards' }}
            >
              <CampaignRow
                campaign={campaign}
                isSelected={selectedCampaignId === campaign.id}
                isViewer={isViewer}
                onSelect={onSelect}
                archiveCampaign={archiveCampaign}
                unarchiveCampaign={unarchiveCampaign}
                deleteCampaign={deleteCampaign}
              />
            </li>
          ))}
        </ul>
      )
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">Renewal campaigns</CardTitle>
        <label className="flex items-center gap-1.5 text-sm font-normal text-muted-foreground">
          <Checkbox checked={showArchived} onCheckedChange={(checked) => setShowArchived(checked === true)} />
          Show archived
        </label>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  )
}
