import { apiGet } from '@/api/client'
import type { AuditEvent } from './types'

export interface AuditEventFilters {
  action?: string
  targetType?: string
  since?: string
  until?: string
}

export function getAuditEvents(filters: AuditEventFilters = {}): Promise<AuditEvent[]> {
  const params = new URLSearchParams()
  if (filters.action) params.set('action', filters.action)
  if (filters.targetType) params.set('targetType', filters.targetType)
  if (filters.since) params.set('since', filters.since)
  if (filters.until) params.set('until', filters.until)

  const query = params.toString()
  return apiGet<AuditEvent[]>(query ? `/audit?${query}` : '/audit')
}
