import { format, formatDistanceToNow, isValid, parseISO } from 'date-fns'

function toDate(value: string | Date): Date {
  return value instanceof Date ? value : parseISO(value)
}

/** e.g. "Aug 28, 2026, 3:12 PM" */
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  if (!isValid(date)) return '—'
  return format(date, 'MMM d, yyyy, h:mm a')
}

/** e.g. "Aug 28, 2026" */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  if (!isValid(date)) return '—'
  return format(date, 'MMM d, yyyy')
}

/** e.g. "3 minutes ago" */
export function formatRelative(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = toDate(value)
  if (!isValid(date)) return '—'
  return formatDistanceToNow(date, { addSuffix: true })
}

export function formatPercent(numerator: number, denominator: number | null | undefined): number {
  if (!denominator || denominator <= 0) return 0
  return Math.round((numerator / denominator) * 1000) / 10
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase()
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase()
}
