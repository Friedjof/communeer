import { Link } from '@tanstack/react-router'
import { Braces, ShieldCheck } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { ErrorState } from '@/components/feedback/ErrorState'
import { formatDate, initials } from '@/lib/format'
import { MaskedPhone } from './MaskedPhone'
import { useMember } from './queries'

interface MemberDrawerProps {
  memberId: string | null
  onOpenChange: (open: boolean) => void
}

export function MemberDrawer({ memberId, onOpenChange }: MemberDrawerProps) {
  const member = useMember(memberId)

  return (
    <Sheet open={memberId !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Member details</SheetTitle>
          <SheetDescription className="sr-only">Member identity, group memberships, and raw metadata.</SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-6 px-4 pb-6">
          {member.isPending ? (
            <ListSkeleton count={4} />
          ) : member.isError || !member.data ? (
            <ErrorState message={member.error?.message ?? 'Member not found.'} />
          ) : (
            <>
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

              <dl className="grid grid-cols-2 gap-3 text-sm">
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
                <div>
                  <dt className="text-muted-foreground">Group memberships</dt>
                  <dd>{member.data.memberships.length}</dd>
                </div>
              </dl>

              <Separator />

              <div>
                <h3 className="mb-2 text-sm font-medium">Group memberships</h3>
                <ul className="flex flex-col gap-2">
                  {member.data.memberships.map((membership) => (
                    <li
                      key={membership.groupId}
                      className="flex items-center justify-between gap-2 rounded-lg border p-3 text-sm"
                    >
                      <div className="flex flex-col">
                        <span className="font-medium">{membership.groupName}</span>
                        <span className="text-xs text-muted-foreground">{membership.communityName}</span>
                        <span className="text-xs text-muted-foreground">Joined {formatDate(membership.joinedAt)}</span>
                      </div>
                      <div className="flex items-center gap-2">
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
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
