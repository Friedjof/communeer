import { ImageIcon, MessageSquare } from 'lucide-react'
import { useEffect, useState } from 'react'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { formatRelative, initials } from '@/lib/format'
import { useGroupMembers, useGroupMessages } from '../queries'

// Same debounce window `DataTable.tsx`'s own search input uses — typing
// shouldn't fire a new request (and reset pagination) on every keystroke.
const SEARCH_DEBOUNCE_MS = 250

interface GroupMessagesTabProps {
  groupId: string
}

export function GroupMessagesTab({ groupId }: GroupMessagesTabProps) {
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [memberId, setMemberId] = useState<string | undefined>(undefined)

  useEffect(() => {
    const timeout = setTimeout(() => setSearch(searchInput), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timeout)
  }, [searchInput])

  const members = useGroupMembers(groupId)
  const messages = useGroupMessages(groupId, { search: search || undefined, memberId })

  const rows = messages.data?.pages.flat() ?? []

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Search</span>
          <Input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search message content…"
            className="w-64"
            aria-label="Search messages"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Member</span>
          <Select
            value={memberId ?? 'all'}
            onValueChange={(value) => setMemberId(value === 'all' ? undefined : value)}
          >
            <SelectTrigger className="w-48" aria-label="Filter by member">
              <SelectValue placeholder="All members" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All members</SelectItem>
              {(members.data ?? []).map((member) => (
                <SelectItem key={member.memberId} value={member.memberId}>
                  {member.displayName}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {messages.isPending ? (
        <ListSkeleton count={6} />
      ) : messages.isError ? (
        <ErrorState message={messages.error?.message} onRetry={() => messages.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          title="No messages"
          description={
            search || memberId
              ? 'No messages match these filters.'
              : "No messages have been recorded for this group yet — Communeer only stores messages received after this feature's rollout."
          }
        />
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {rows.map((message) => (
              <li key={message.id} className="flex items-start gap-2.5 rounded-lg border p-3 text-sm">
                <Avatar className="size-8 shrink-0">
                  <AvatarImage src={message.avatarUrl ?? undefined} alt="" />
                  <AvatarFallback className="text-xs">{initials(message.displayName ?? '?')}</AvatarFallback>
                </Avatar>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{message.displayName ?? 'Unknown member'}</span>
                    {message.messageType === 'media' ? (
                      <Badge variant="secondary" className="gap-1">
                        <ImageIcon className="size-3" />
                        Media
                      </Badge>
                    ) : null}
                    <span className="text-xs text-muted-foreground">{formatRelative(message.sentAt)}</span>
                  </div>
                  <p className="whitespace-pre-wrap break-words text-muted-foreground">{message.content}</p>
                </div>
              </li>
            ))}
          </ul>
          {messages.hasNextPage ? (
            <Button
              variant="outline"
              size="sm"
              className="self-center"
              disabled={messages.isFetchingNextPage}
              onClick={() => messages.fetchNextPage()}
            >
              {messages.isFetchingNextPage ? 'Loading…' : 'Load older'}
            </Button>
          ) : null}
        </>
      )}
    </div>
  )
}
