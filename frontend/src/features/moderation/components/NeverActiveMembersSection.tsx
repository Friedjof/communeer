import { UserX } from 'lucide-react'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { formatDate, initials } from '@/lib/format'
import { useDismissModerationItem } from '../queries'
import type { NeverActiveMember } from '../types'
import { isModerationItemDismissing, MODERATION_ROW_TRIGGER_CLASS, ModerationRow } from './ModerationRow'
import { ModerationSectionCard } from './ModerationSectionCard'

interface NeverActiveMembersSectionProps {
  communityId: string
  members: NeverActiveMember[]
  onSelectMember: (memberId: string) => void
}

export function NeverActiveMembersSection({ communityId, members, onSelectMember }: NeverActiveMembersSectionProps) {
  const dismiss = useDismissModerationItem(communityId)

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
        <ul className="flex flex-col gap-2">
          {members.map((member) => (
            <ModerationRow
              key={member.memberId}
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
      )}
    </ModerationSectionCard>
  )
}
