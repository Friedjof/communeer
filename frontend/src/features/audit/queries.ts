import { useQuery } from '@tanstack/react-query'
import * as auditApi from './api'
import type { AuditEventFilters } from './api'

export const auditKeys = {
  all: ['audit'] as const,
  list: (filters: AuditEventFilters) => ['audit', filters] as const,
}

export function useAuditEvents(filters: AuditEventFilters = {}) {
  return useQuery({
    queryKey: auditKeys.list(filters),
    queryFn: () => auditApi.getAuditEvents(filters),
  })
}
