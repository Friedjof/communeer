import { apiGet } from '@/api/client'
import type { AuditEvent } from './types'

export function getAuditEvents(): Promise<AuditEvent[]> {
  return apiGet<AuditEvent[]>('/audit')
}
