export interface AuditEvent {
  id: string
  actorUsername: string | null
  action: string
  targetType: string | null
  targetId: string | null
  detail: Record<string, unknown> | null
  occurredAt: string
}
