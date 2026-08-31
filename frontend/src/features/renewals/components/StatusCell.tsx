import { AlertTriangle, CheckCircle2, Clock, UserX, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { RenewalConfirmation } from '../types'

export function StatusCell({ confirmation }: { confirmation: RenewalConfirmation }) {
  if (confirmation.removedAt) {
    return (
      <Badge variant="destructive" className="gap-1">
        <UserX className="size-3" />
        Removed
      </Badge>
    )
  }
  if (confirmation.status === 'confirmed') {
    return (
      <Badge variant="secondary" className="gap-1">
        <CheckCircle2 className="size-3" />
        Confirmed
      </Badge>
    )
  }
  if (confirmation.declinedAt) {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="size-3" />
        Declined
      </Badge>
    )
  }
  if (confirmation.isExpired) {
    return (
      <Badge className="gap-1 bg-warning text-warning-foreground">
        <AlertTriangle className="size-3" />
        Pending — overdue
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1 text-muted-foreground">
      <Clock className="size-3" />
      Pending
    </Badge>
  )
}
