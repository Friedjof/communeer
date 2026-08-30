import type { RowData } from '@tanstack/react-table'
import { DataTable, type ColumnDef, type DataTableExportColumn } from '@/components/data/DataTable'

interface MemberTableProps<TData extends RowData> {
  data: TData[]
  // biome-ignore lint/suspicious/noExplicitAny: see DataTable's ColumnDef comment
  columns: ColumnDef<TData, any>[]
  onRowClick?: (row: TData) => void
  searchPlaceholder?: string
  emptyMessage?: string
  exportFileName?: string
  exportColumns?: DataTableExportColumn<TData>[]
}

/** Thin wrapper over the generic DataTable, reused for community-wide and per-group member lists. */
export function MemberTable<TData extends RowData>({
  data,
  columns,
  onRowClick,
  searchPlaceholder = 'Search members…',
  emptyMessage = 'No members found.',
  exportFileName,
  exportColumns,
}: MemberTableProps<TData>) {
  return (
    <DataTable
      data={data}
      columns={columns}
      onRowClick={onRowClick}
      searchPlaceholder={searchPlaceholder}
      emptyMessage={emptyMessage}
      exportFileName={exportFileName}
      exportColumns={exportColumns}
    />
  )
}
