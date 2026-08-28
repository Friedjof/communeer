import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { TableSkeleton } from '@/components/feedback/LoadingSkeletons'
import { MemberTable } from '@/features/members/MemberTable'
import { useSuggestionColumns } from '../columns'
import { useRenewalSuggestions } from '../queries'
import type { RenewalSuggestion } from '../types'
import { StartRenewalDialog } from './StartRenewalDialog'

interface StartRenewalSectionProps {
  communityId: string
  onCampaignCreated: (campaignId: string) => void
}

export function StartRenewalSection({ communityId, onCampaignCreated }: StartRenewalSectionProps) {
  const suggestions = useRenewalSuggestions(communityId)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [dialogOpen, setDialogOpen] = useState(false)

  function toggle(memberId: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(memberId)) {
        next.delete(memberId)
      } else {
        next.add(memberId)
      }
      return next
    })
  }

  const columns = useSuggestionColumns(selected, toggle)

  const selectedMembers = useMemo(
    () => (suggestions.data ?? []).filter((member) => selected.has(member.memberId)),
    [suggestions.data, selected],
  )

  let body: ReactNode
  if (suggestions.isPending) {
    body = <TableSkeleton />
  } else if (suggestions.isError || !suggestions.data) {
    body = <ErrorState message={suggestions.error?.message} onRetry={() => suggestions.refetch()} />
  } else if (suggestions.data.length === 0) {
    body = (
      <EmptyState
        title="No candidates right now"
        description="Every non-admin member is either already tracked or there's nobody to review yet."
      />
    )
  } else {
    body = (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setSelected(new Set(suggestions.data.map((m) => m.memberId)))}>
              Select all
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())} disabled={selected.size === 0}>
              Clear selection
            </Button>
          </div>
          <Button disabled={selected.size === 0} onClick={() => setDialogOpen(true)}>
            Start renewal for {selected.size} member{selected.size === 1 ? '' : 's'}
          </Button>
        </div>
        <MemberTable<RenewalSuggestion>
          data={suggestions.data}
          columns={columns}
          searchPlaceholder="Search candidates…"
          emptyMessage="No candidates found."
        />
      </div>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Start a renewal round</CardTitle>
        <p className="text-sm text-muted-foreground">
          Select members to confirm, then post the request yourself in WhatsApp. Activity data isn't available yet —
          this list is sorted by tenure and role only, never by inferred behavior.
        </p>
      </CardHeader>
      <CardContent>{body}</CardContent>

      <StartRenewalDialog
        communityId={communityId}
        members={selectedMembers}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={(campaignId) => {
          setSelected(new Set())
          onCampaignCreated(campaignId)
        }}
      />
    </Card>
  )
}
