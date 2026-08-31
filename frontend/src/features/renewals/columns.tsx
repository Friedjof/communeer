import { legacyCreateColumnHelper as createColumnHelper } from '@tanstack/react-table/legacy'
import { useMemo } from 'react'
import type { ColumnDef } from '@/components/data/DataTable'
import { ActivityColumnHeader, MessageActivityBadge } from '@/components/data/MessageActivityCell'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Checkbox } from '@/components/ui/checkbox'
import { MaskedPhone } from '@/features/members/components/MaskedPhone'
import { formatDate, initials } from '@/lib/format'
import type { RenewalSuggestion } from './types'

const columnHelper = createColumnHelper<RenewalSuggestion>()

/**
 * Suggestion table columns, parameterized by the current selection so
 * checkbox state lives in the parent (`GroupRenewalsTab`/`StartRenewalSection`)
 * rather than inside the table itself.
 */
export function useSuggestionColumns(
  selected: Set<string>,
  onToggle: (memberId: string) => void,
  // biome-ignore lint/suspicious/noExplicitAny: see DataTable's ColumnDef comment
): ColumnDef<RenewalSuggestion, any>[] {
  return useMemo(
    () => [
      columnHelper.display({
        id: 'select',
        header: 'Select',
        cell: (info) => {
          const memberId = info.row.original.memberId
          return (
            <Checkbox
              checked={selected.has(memberId)}
              onCheckedChange={() => onToggle(memberId)}
              onClick={(event) => event.stopPropagation()}
              aria-label={`Select ${info.row.original.displayName}`}
            />
          )
        },
        enableSorting: false,
        enableHiding: false,
      }),
      columnHelper.accessor('displayName', {
        header: 'Member',
        cell: (info) => (
          <div className="flex items-center gap-2.5">
            <Avatar className="size-8">
              {info.row.original.avatarUrl ? <AvatarImage src={info.row.original.avatarUrl} alt="" /> : null}
              <AvatarFallback className="text-xs">{initials(info.getValue())}</AvatarFallback>
            </Avatar>
            <div className="flex flex-col">
              <span className="font-medium leading-tight">{info.getValue()}</span>
              <span className="text-xs text-muted-foreground leading-tight">{info.row.original.waId}</span>
            </div>
          </div>
        ),
      }),
      columnHelper.accessor('phoneNumberMasked', {
        header: 'Phone',
        cell: (info) => <MaskedPhone value={info.getValue()} />,
      }),
      columnHelper.accessor('joinedAt', {
        header: 'Joined',
        cell: (info) => formatDate(info.getValue()),
      }),
      columnHelper.accessor('lastMessageAt', {
        header: ActivityColumnHeader,
        cell: (info) => <MessageActivityBadge lastMessageAt={info.getValue()} />,
      }),
    ],
    [selected, onToggle],
  )
}
