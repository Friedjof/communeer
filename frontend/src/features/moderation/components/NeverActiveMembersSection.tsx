import { UserX } from 'lucide-react'
import { useState } from 'react'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { formatDate, formatNumber, initials } from '@/lib/format'
import { useDismissModerationItem } from '../queries'
import type { NeverActiveMember } from '../types'
import { isModerationItemDismissing, MODERATION_ROW_TRIGGER_CLASS } from './moderationRowHelpers'
import { ModerationRow } from './ModerationRow'
import { ModerationSectionCard } from './ModerationSectionCard'

// A large community can have thousands of never-active members — rendering
// every row unconditionally made this section (and the page it sits in)
// tens of thousands of pixels tall. Cap the initial render and let an admin
// opt into the full list, same "don't render what nobody's looking at yet"
// posture as `DataTable`'s pagination.
const INITIAL_VISIBLE_COUNT = 25

interface NeverActiveMembersSectionProps {
  communityId: string
  members: NeverActiveMember[]
  onSelectMember: (memberId: string) => void
}

export function NeverActiveMembersSection({ communityId, members, onSelectMember }: NeverActiveMembersSectionProps) {
  const dismiss = useDismissModerationItem(communityId)
  const [showAll, setShowAll] = useState(false)

  const visibleMembers = showAll ? members : members.slice(0, INITIAL_VISIBLE_COUNT)
  const hiddenCount = members.length - visibleMembers.length

  return (
    <ModerationSectionCard
      title="Never-active members"
      description="Members who have never posted a message in any of this community's groups (admins excluded)."
    >
      {members.length === 0 ? (
        <EmptyState
          icon={UserX}
          title="No never-active members"
          description="Every non-admin member has posted at least once."
        />
      ) : (
        <>
        <ul className="flex flex-col gap-2">
          {visibleMembers.map((member, index) => (
            <ModerationRow
              key={member.memberId}
              index={index}
              isDismissing={isModerationItemDismissing(dismiss, member.memberId)}
              onDismiss={() => dismiss.mutate({ section: 'never_active_members', targetId: member.memberId })}
            >
              <button
                type="button"
                onClick={() => onSelectMember(member.memberId)}
                className={`${MODERATION_ROW_TRIGGER_CLASS} text-left`}
              >
                <div className="flex items-center gap-2.5">
                  <Avatar className="size-8">
                    {member.avatarUrl ? <AvatarImage src={member.avatarUrl} alt="" /> : null}
                    <AvatarFallback className="text-xs">{initials(member.displayName)}</AvatarFallback>
                  </Avatar>
                  <div className="flex flex-col">
                    <span className="font-medium leading-tight">{member.displayName}</span>
                    <span className="text-xs leading-tight text-muted-foreground">{member.waId}</span>
                  </div>
                </div>
                <span className="text-muted-foreground">Joined {formatDate(member.joinedAt)}, never posted</span>
              </button>
            </ModerationRow>
          ))}
        </ul>
        {hiddenCount > 0 || showAll ? (
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {showAll
                ? `Showing all ${formatNumber(members.length)} never-active members.`
                : `Showing ${formatNumber(visibleMembers.length)} of ${formatNumber(members.length)}.`}
            </span>
            <Button variant="outline" size="sm" onClick={() => setShowAll((prev) => !prev)}>
              {showAll ? 'Show fewer' : `Show all ${formatNumber(hiddenCount)} more`}
            </Button>
          </div>
        ) : null}
        </>
      )}
    </ModerationSectionCard>
  )
}
