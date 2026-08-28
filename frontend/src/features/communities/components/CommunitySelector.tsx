import { useNavigate } from '@tanstack/react-router'
import { Users } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useUiStore } from '@/lib/uiStore'
import { useCommunities } from '../queries'

interface CommunitySelectorProps {
  currentCommunityId?: string
}

export function CommunitySelector({ currentCommunityId }: CommunitySelectorProps) {
  const { data: communities, isPending } = useCommunities()
  const navigate = useNavigate()
  const setSelectedCommunityId = useUiStore((state) => state.setSelectedCommunityId)

  if (isPending) {
    return <div className="h-9 w-44 animate-pulse rounded-md bg-muted" />
  }

  if (!communities || communities.length === 0) {
    return null
  }

  return (
    <Select
      value={currentCommunityId}
      onValueChange={(value) => {
        setSelectedCommunityId(value)
        void navigate({ to: '/c/$communityId', params: { communityId: value } })
      }}
    >
      <SelectTrigger className="w-36 sm:w-52" aria-label="Select community">
        <Users className="size-4 text-muted-foreground" />
        <SelectValue placeholder="Select a community" />
      </SelectTrigger>
      <SelectContent>
        {communities.map((community) => (
          <SelectItem key={community.id} value={community.id}>
            {community.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
