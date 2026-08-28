import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { useGroup } from '../queries'
import { RawMetadataViewer } from './RawMetadataViewer'

interface GroupAdvancedTabProps {
  groupId: string
}

export function GroupAdvancedTab({ groupId }: GroupAdvancedTabProps) {
  const group = useGroup(groupId, true)

  if (group.isPending) {
    return <ListSkeleton count={6} />
  }

  if (group.isError || !group.data) {
    return <ErrorState message={group.error?.message} onRetry={() => group.refetch()} />
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        Raw provider metadata as returned by the WhatsApp integration (WPPConnect-shaped payload).
      </p>
      <RawMetadataViewer data={group.data.rawMetadata ?? {}} />
    </div>
  )
}
