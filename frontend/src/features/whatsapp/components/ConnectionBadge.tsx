import { AlertTriangle, CheckCircle2, Loader2, QrCode, WifiOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { WhatsAppConnectionState } from '../types'

interface ConnectionBadgeProps {
  state: WhatsAppConnectionState
  className?: string
}

const STATE_CONFIG: Record<
  WhatsAppConnectionState,
  { label: string; icon: typeof CheckCircle2; className: string; spin?: boolean }
> = {
  connected: {
    label: 'Connected',
    icon: CheckCircle2,
    className: 'border-primary/30 text-primary',
  },
  connecting: {
    label: 'Connecting…',
    icon: Loader2,
    className: 'border-border text-muted-foreground',
    spin: true,
  },
  qr_pending: {
    label: 'Scan QR code',
    icon: QrCode,
    className: 'border-amber-500/30 text-amber-600 dark:text-amber-400',
  },
  disconnected: {
    label: 'Disconnected',
    icon: WifiOff,
    className: 'border-border text-muted-foreground',
  },
  error: {
    label: 'Connection error',
    icon: AlertTriangle,
    className: 'border-destructive/30 text-destructive',
  },
}

/** Icon + text status indicator for the WhatsApp connection state. Never relies on color alone. */
export function ConnectionBadge({ state, className }: ConnectionBadgeProps) {
  const { label, icon: Icon, className: stateClassName, spin } = STATE_CONFIG[state]

  return (
    <Badge variant="outline" className={cn('items-center gap-1.5', stateClassName, className)}>
      <Icon className={cn('size-3', spin && 'animate-spin')} />
      {label}
    </Badge>
  )
}
