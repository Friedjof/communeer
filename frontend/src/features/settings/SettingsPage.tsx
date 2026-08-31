import { Link } from '@tanstack/react-router'
import { Wifi } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { useSession } from '@/features/auth/queries'
import { useWhatsAppStatus } from '@/features/whatsapp/queries'
import type { WhatsAppConnectionState } from '@/features/whatsapp/types'
import { UsersPage } from '@/features/users/UsersPage'

const STATE_LABEL: Record<WhatsAppConnectionState, string> = {
  connected: 'Connected',
  disconnected: 'Disconnected',
  qr_pending: 'Waiting for QR scan',
  connecting: 'Connecting…',
  error: 'Error',
}

const STATE_BADGE_VARIANT: Record<WhatsAppConnectionState, 'default' | 'secondary' | 'destructive'> = {
  connected: 'default',
  disconnected: 'secondary',
  qr_pending: 'secondary',
  connecting: 'secondary',
  error: 'destructive',
}

function ConnectionTab() {
  const status = useWhatsAppStatus()

  if (status.isPending) {
    return null
  }

  if (status.isError || !status.data) {
    return <ErrorState message={status.error?.message} onRetry={() => status.refetch()} />
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <Wifi className="size-5 text-muted-foreground" />
        <div>
          <p className="font-medium">WhatsApp connection</p>
          <p className="text-sm text-muted-foreground">
            {status.data.detail ?? 'Status of the WhatsApp session this dashboard syncs from.'}
          </p>
        </div>
        <Badge variant={STATE_BADGE_VARIANT[status.data.state]} className="ml-auto">
          {STATE_LABEL[status.data.state]}
        </Badge>
      </div>
      {status.data.state !== 'connected' ? (
        <Button asChild variant="outline" className="w-fit">
          <Link to="/setup/whatsapp">Reconnect</Link>
        </Button>
      ) : null}
      <p className="text-xs text-muted-foreground">
        Provider connection details (server URL, session, secret key) are configured via environment variables at
        deploy time and aren't editable here.
      </p>
    </div>
  )
}

function TeamTab() {
  const session = useSession()

  if (session.data?.role !== 'owner') {
    return (
      <EmptyState
        title="Owner access required"
        description="Only the workspace owner can view and manage other users."
      />
    )
  }

  return <UsersPage />
}

export function SettingsPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <Tabs defaultValue="team">
        <TabsList>
          <TabsTrigger value="team">Team</TabsTrigger>
          <TabsTrigger value="connection">Connection</TabsTrigger>
        </TabsList>
        <TabsContent value="team">
          <TeamTab />
        </TabsContent>
        <TabsContent value="connection">
          <ConnectionTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
