import { Link } from '@tanstack/react-router'
import { Activity, Braces, ShieldCheck, Users } from 'lucide-react'
import { ActivityBar } from '@/components/data/ActivityBar'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'
import { StatTile } from '@/features/communities/components/StatTile'
import { formatDate, formatRelative, initials } from '@/lib/format'
import { useMember } from '../queries'
import type { MemberMembership } from '../types'
import { MaskedPhone } from './MaskedPhone'
import { MemberActivityChart } from './MemberActivityChart'

interface MemberDetailDialogProps {
  memberId: string | null
  onOpenChange: (open: boolean) => void
}

/** The single most recent activity across every group this member belongs
 * to — used for the summary stat tile, distinct from the per-group
 * `ActivityBar`s shown further down. */
function mostRecentActivity(memberships: MemberMembership[]): MemberMembership | null {
  let latest: MemberMembership | null = null
  for (const membership of memberships) {
    if (!membership.lastActivityAt) continue
    if (!latest?.lastActivityAt || new Date(membership.lastActivityAt) > new Date(latest.lastActivityAt)) {
      latest = membership
    }
  }
  return latest
}

export function MemberDetailDialog({ memberId, onOpenChange }: MemberDetailDialogProps) {
  const member = useMember(memberId)
  const memberships = member.data?.memberships ?? []
  const adminCount = memberships.filter((membership) => membership.isAdmin).length
  const latestActivity = mostRecentActivity(memberships)

  return (
    <Dialog open={memberId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Member details</DialogTitle>
          <DialogDescription className="sr-only">
            Member identity, activity statistics, and group memberships.
          </DialogDescription>
        </DialogHeader>

        {member.isPending ? (
          <ListSkeleton count={4} />
        ) : member.isError || !member.data ? (
          <ErrorState message={member.error?.message ?? 'Member not found.'} />
        ) : (
          <div className="flex flex-col gap-6">
            <div className="flex items-center gap-3">
              <Avatar className="size-12">
                {member.data.avatarUrl ? <AvatarImage src={member.data.avatarUrl} alt="" /> : null}
                <AvatarFallback>{initials(member.data.displayName)}</AvatarFallback>
              </Avatar>
              <div>
                <p className="text-lg font-semibold">{member.data.displayName}</p>
                <p className="text-sm text-muted-foreground">{member.data.waId}</p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <StatTile label="Groups" value={memberships.length} icon={Users} />
              <StatTile label="Admin in" value={adminCount} icon={ShieldCheck} />
              <StatTile
                label="Last activity"
                value={
                  latestActivity?.lastActivityAt ? formatRelative(latestActivity.lastActivityAt) : 'No activity yet'
                }
                icon={Activity}
              />
            </div>

            <dl className="grid grid-cols-3 gap-3 text-sm">
              <div>
                <dt className="text-muted-foreground">Phone</dt>
                <dd>
                  <MaskedPhone value={member.data.phoneNumberMasked} />
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">First seen</dt>
                <dd>{formatDate(member.data.firstSeenAt)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Business account</dt>
                <dd>{member.data.isBusiness ? 'Yes' : 'No'}</dd>
              </div>
            </dl>

            <Separator />

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div>
                <h3 className="mb-2 text-sm font-medium">Activity recency by group</h3>
                <MemberActivityChart memberships={memberships} />
              </div>

              <div>
                <h3 className="mb-2 text-sm font-medium">Activity by group</h3>
                <ul className="flex max-h-60 flex-col gap-2 overflow-y-auto pr-1">
                  {memberships.map((membership) => (
                    <li
                      key={membership.groupId}
                      className="flex flex-col gap-2 rounded-lg border p-3 text-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate font-medium">{membership.groupName}</p>
                          <p className="truncate text-xs text-muted-foreground">{membership.communityName}</p>
                          <p className="text-xs text-muted-foreground">Joined {formatDate(membership.joinedAt)}</p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          {membership.isAdmin ? (
                            <Badge variant="secondary" className="gap-1">
                              <ShieldCheck className="size-3" />
                              Admin
                            </Badge>
                          ) : null}
                          {membership.status === 'pending' ? <Badge>Pending</Badge> : null}
                          <Link
                            to="/c/$communityId/groups/$groupId"
                            params={{ communityId: membership.communityId, groupId: membership.groupId }}
                            search={{ tab: 'advanced' }}
                            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                            title="View raw metadata"
                          >
                            <Braces className="size-3.5" />
                          </Link>
                        </div>
                      </div>
                      <ActivityBar
                        lastActivityType={membership.lastActivityType}
                        lastActivityAt={membership.lastActivityAt}
                        lastActivityContent={membership.lastActivityContent}
                        truncateAt={null}
                        showContentInline
                      />
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
