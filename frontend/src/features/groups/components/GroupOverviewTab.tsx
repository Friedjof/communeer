import { Check, Clock, Copy, Link2, ShieldCheck, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { CAPACITY_ATTENTION_THRESHOLD, CapacityBar } from '@/components/data/CapacityBar'
import { ExpandableText } from '@/components/data/ExpandableText'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { StatTile } from '@/features/communities/components/StatTile'
import { formatNumber, formatPercent, formatRelative, initials } from '@/lib/format'
import { useGroupInviteLink, useGroupMembers } from '../queries'
import type { GroupDetail, GroupMemberRow } from '../types'
import { GroupActivityChart } from './GroupActivityChart'
import { GroupHistoryChart } from './GroupHistoryChart'

/** Fetched on demand only (see `useGroupInviteLink`) — `null` is a real,
 * honest answer (the connected account can't generate one for this group
 * right now), not an error, so it's shown as plain text rather than an
 * `ErrorState`. */
function GroupInviteLink({ groupId }: { groupId: string }) {
  const inviteLink = useGroupInviteLink(groupId)
  const [copied, setCopied] = useState(false)

  async function handleCopy(link: string) {
    await navigator.clipboard.writeText(link)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!inviteLink.isFetched) {
    return (
      <Button variant="outline" size="sm" className="gap-1.5" onClick={() => inviteLink.refetch()} disabled={inviteLink.isFetching}>
        <Link2 className="size-3.5" />
        {inviteLink.isFetching ? 'Fetching…' : 'Get invite link'}
      </Button>
    )
  }

  if (inviteLink.isError || !inviteLink.data?.inviteLink) {
    return <p className="text-xs text-muted-foreground">No invite link available for this group right now.</p>
  }

  const link = inviteLink.data.inviteLink
  return (
    <div className="flex items-center gap-1.5">
      <p className="truncate font-mono text-xs">{link}</p>
      <Button variant="ghost" size="icon-sm" aria-label="Copy invite link" onClick={() => handleCopy(link)}>
        {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
      </Button>
    </div>
  )
}

interface GroupOverviewTabProps {
  group: GroupDetail
}

/** Every member with admin rights in this group, super admins first. Kept
 * lightweight (name + avatar + role badge) — a supplementary section, not a
 * replacement for the full Members tab. */
function AdminList({ members }: { members: GroupMemberRow[] }) {
  const admins = members
    .filter((member) => member.status === 'member' && member.isAdmin)
    .sort((a, b) => Number(b.isSuperAdmin) - Number(a.isSuperAdmin) || a.displayName.localeCompare(b.displayName))

  if (admins.length === 0) {
    return <p className="text-sm text-muted-foreground">No admins found.</p>
  }

  return (
    <ul className="flex flex-col gap-2">
      {admins.map((member) => (
        <li key={member.memberId} className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm">
          <div className="flex min-w-0 items-center gap-2.5">
            <Avatar className="size-8 shrink-0">
              {member.avatarUrl ? <AvatarImage src={member.avatarUrl} alt="" /> : null}
              <AvatarFallback className="text-xs">{initials(member.displayName)}</AvatarFallback>
            </Avatar>
            <span className="truncate font-medium">{member.displayName}</span>
          </div>
          {member.isSuperAdmin ? (
            <Badge className="shrink-0">Super admin</Badge>
          ) : (
            <Badge variant="secondary" className="shrink-0">
              Admin
            </Badge>
          )}
        </li>
      ))}
    </ul>
  )
}

type ActivityBucket = 'message' | 'reaction' | 'view' | 'never'

const ACTIVITY_META: Record<ActivityBucket, { label: string; barColor: string; dotColor: string }> = {
  message: { label: 'Messaged', barColor: 'bg-primary', dotColor: 'bg-primary' },
  reaction: { label: 'Reacted only', barColor: 'bg-success', dotColor: 'bg-success' },
  view: { label: 'Viewed only', barColor: 'bg-muted-foreground', dotColor: 'bg-muted-foreground' },
  never: { label: 'Never active', barColor: 'bg-muted', dotColor: 'bg-muted' },
}

const ACTIVITY_ORDER: ActivityBucket[] = ['message', 'reaction', 'view', 'never']

/** Client-side breakdown of `lastActivityType` across this group's active
 * members — a segmented bar plus counts, deliberately simple rather than a
 * new chart type. */
function ActivityBreakdown({ members }: { members: GroupMemberRow[] }) {
  const activeMembers = members.filter((member) => member.status === 'member')
  const counts: Record<ActivityBucket, number> = { message: 0, reaction: 0, view: 0, never: 0 }
  for (const member of activeMembers) {
    counts[(member.lastActivityType ?? 'never') as ActivityBucket] += 1
  }
  const total = activeMembers.length

  if (total === 0) {
    return <p className="text-sm text-muted-foreground">No members yet.</p>
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border p-3">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        {ACTIVITY_ORDER.filter((bucket) => counts[bucket] > 0).map((bucket) => (
          <div
            key={bucket}
            className={ACTIVITY_META[bucket].barColor}
            style={{ width: `${(counts[bucket] / total) * 100}%` }}
          />
        ))}
      </div>
      <ul className="flex flex-col gap-1.5 text-sm">
        {ACTIVITY_ORDER.map((bucket) => (
          <li key={bucket} className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-muted-foreground">
              <span className={`size-2 shrink-0 rounded-full ${ACTIVITY_META[bucket].dotColor}`} />
              {ACTIVITY_META[bucket].label}
            </span>
            <span className="tabular-nums font-medium">{formatNumber(counts[bucket])}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function GroupOverviewTab({ group }: GroupOverviewTabProps) {
  const members = useGroupMembers(group.id)

  const isNearCapacity =
    Boolean(group.memberLimit) && formatPercent(group.memberCount, group.memberLimit) >= CAPACITY_ATTENTION_THRESHOLD

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start gap-4">
        <Avatar className="size-16 shrink-0">
          {group.pictureUrl ? <AvatarImage src={group.pictureUrl} alt="" /> : null}
          <AvatarFallback className="text-lg">{initials(group.name)}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-medium text-muted-foreground">Description</h2>
          <ExpandableText text={group.description} title={`${group.name} — description`} className="mt-1" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div>
          <h2 className="text-sm font-medium text-muted-foreground">Community</h2>
          <p className="mt-1 font-medium">{group.communityName}</p>
        </div>
        <div>
          <h2 className="text-sm font-medium text-muted-foreground">Type</h2>
          <p className="mt-1">
            {group.isAnnouncementGroup ? <Badge variant="secondary">Announcement group</Badge> : 'Regular group'}
          </p>
        </div>
        <div>
          <h2 className="text-sm font-medium text-muted-foreground">WhatsApp ID</h2>
          <p className="mt-1 font-mono text-xs">{group.waId}</p>
        </div>
        <div>
          <h2 className="text-sm font-medium text-muted-foreground">Invite link</h2>
          <div className="mt-1">
            <GroupInviteLink groupId={group.id} />
          </div>
        </div>
      </div>

      <div className="max-w-sm">
        <div className="mb-2 flex items-center gap-2">
          <h2 className="text-sm font-medium text-muted-foreground">Capacity</h2>
          {isNearCapacity ? <Badge className="bg-destructive text-destructive-foreground">Near capacity</Badge> : null}
        </div>
        <CapacityBar memberCount={group.memberCount} memberLimit={group.memberLimit} />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatTile label="Admins" value={group.adminCount} icon={ShieldCheck} />
        <StatTile
          label="Pending requests"
          value={group.pendingRequestCount}
          icon={UserPlus}
          tone={group.pendingRequestCount > 0 ? 'warning' : 'default'}
        />
        <StatTile
          label="Last activity"
          value={group.lastMessageAt ? formatRelative(group.lastMessageAt) : 'No activity yet'}
          icon={Clock}
        />
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Member growth</h2>
        <GroupHistoryChart communityId={group.communityId} groupId={group.id} />
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Group activity</h2>
        <p className="mb-2 text-xs text-muted-foreground">
          How recently members were last active (message, reaction, or view) — a snapshot, not a trend over time.
        </p>
        {members.isPending ? (
          <ListSkeleton count={3} />
        ) : members.isError || !members.data ? (
          <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
        ) : (
          <GroupActivityChart members={members.data} />
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Admins</h2>
          {members.isPending ? (
            <ListSkeleton count={3} />
          ) : members.isError || !members.data ? (
            <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
          ) : (
            <AdminList members={members.data} />
          )}
        </div>
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Activity breakdown</h2>
          {members.isPending ? (
            <ListSkeleton count={3} />
          ) : members.isError || !members.data ? (
            <ErrorState message={members.error?.message} onRetry={() => members.refetch()} />
          ) : (
            <ActivityBreakdown members={members.data} />
          )}
        </div>
      </div>
    </div>
  )
}
