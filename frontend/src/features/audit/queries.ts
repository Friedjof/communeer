import { useQuery } from '@tanstack/react-query'
import * as auditApi from './api'

export const auditKeys = {
  all: ['audit'] as const,
}

export function useAuditEvents() {
  return useQuery({
    queryKey: auditKeys.all,
    queryFn: auditApi.getAuditEvents,
  })
}
