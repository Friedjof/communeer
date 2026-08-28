import { useNavigate } from '@tanstack/react-router'
import { Loader2, MessageCircle } from 'lucide-react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useConnectWhatsApp, useDiscoverAndSync, useWhatsAppStatus } from './queries'
import type { WhatsAppConnectionState } from './types'

export function WhatsAppSetupPage() {
  const navigate = useNavigate()
  const status = useWhatsAppStatus()
  const connect = useConnectWhatsApp()
  const discoverAndSync = useDiscoverAndSync()

  const connectError =
    connect.error instanceof ApiError ? connect.error.message : connect.error ? 'Something went wrong. Please try again.' : null
  const discoverError =
    discoverAndSync.error instanceof ApiError
      ? discoverAndSync.error.message
      : discoverAndSync.error
        ? 'Something went wrong. Please try again.'
        : null

  function handleDiscover() {
    discoverAndSync.mutate(undefined, {
      onSuccess: () => {
        void navigate({ to: '/' })
      },
    })
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <div className="mb-2 flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <MessageCircle className="size-6" />
          </div>
          <CardTitle className="text-xl">Connect WhatsApp</CardTitle>
          <CardDescription>Link a WhatsApp account to start syncing communities.</CardDescription>
        </CardHeader>
        <CardContent>
          {status.isPending ? (
            <div className="flex flex-col items-center gap-3 py-4">
              <Skeleton className="size-12 rounded-full" />
              <Skeleton className="h-4 w-40" />
            </div>
          ) : null}

          {!status.isPending && status.data ? (
            <StatusBody
              state={status.data.state}
              detail={status.data.detail}
              qrCodeDataUrl={status.data.qrCodeDataUrl}
              onConnect={() => connect.mutate()}
              connectPending={connect.isPending}
              connectError={connectError}
              onDiscover={handleDiscover}
              discoverPending={discoverAndSync.isPending}
              discoverError={discoverError}
            />
          ) : null}

          {!status.isPending && !status.data ? (
            <p className="text-center text-sm text-muted-foreground">Unable to load WhatsApp connection status.</p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}

interface StatusBodyProps {
  state: WhatsAppConnectionState
  detail: string | null
  qrCodeDataUrl: string | null
  onConnect: () => void
  connectPending: boolean
  connectError: string | null
  onDiscover: () => void
  discoverPending: boolean
  discoverError: string | null
}

function StatusBody({
  state,
  detail,
  qrCodeDataUrl,
  onConnect,
  connectPending,
  connectError,
  onDiscover,
  discoverPending,
  discoverError,
}: StatusBodyProps) {
  if (state === 'disconnected' || state === 'error') {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-center text-sm text-muted-foreground">
          {state === 'error'
            ? 'WhatsApp connection ran into a problem.'
            : 'No WhatsApp account is currently linked to this dashboard.'}
        </p>
        {state === 'error' && detail ? <p className="text-center text-sm text-destructive">{detail}</p> : null}
        {connectError ? (
          <p role="alert" className="text-center text-sm text-destructive">
            {connectError}
          </p>
        ) : null}
        <Button className="w-full" onClick={onConnect} disabled={connectPending}>
          {connectPending ? 'Connecting…' : 'Connect WhatsApp'}
        </Button>
      </div>
    )
  }

  if (state === 'qr_pending') {
    return (
      <div className="flex flex-col items-center gap-4">
        <p className="text-center text-sm text-muted-foreground">
          Open WhatsApp on your phone → Settings → Linked devices → Link a device, then scan this code.
        </p>
        {qrCodeDataUrl ? (
          <img src={qrCodeDataUrl} alt="WhatsApp QR code" className="size-56 rounded-md border" />
        ) : (
          <Skeleton className="size-56 rounded-md" />
        )}
        <p className="text-xs text-muted-foreground">This page updates automatically once you scan.</p>
      </div>
    )
  }

  if (state === 'connecting') {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <Loader2 className="size-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Finishing connection…</p>
      </div>
    )
  }

  // connected
  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-sm text-muted-foreground">
        WhatsApp is connected. Discover your communities to start syncing them into Communeer.
      </p>
      {discoverError ? (
        <p role="alert" className="text-center text-sm text-destructive">
          {discoverError}
        </p>
      ) : null}
      <Button className="w-full" onClick={onDiscover} disabled={discoverPending}>
        {discoverPending ? 'Discovering…' : 'Discover communities'}
      </Button>
    </div>
  )
}
