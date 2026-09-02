import { useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { Loader2, MessageCircle } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { communityKeys } from '@/features/communities/queries'
import { useSession } from '@/features/auth/queries'
import { useConnectWhatsApp, useDiscoverAndSync, useWhatsAppStatus, whatsappKeys } from './queries'
import type { WhatsAppConnectionState } from './types'

export function WhatsAppSetupPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const status = useWhatsAppStatus()
  const connect = useConnectWhatsApp()
  const discoverAndSync = useDiscoverAndSync()
  const session = useSession()
  const isViewer = session.data?.role === 'viewer'

  // `POST /whatsapp/connect` returns almost immediately (it only kicks off
  // WPPConnect's own session startup, it doesn't wait for a QR code) — the
  // status polling then sees `disconnected` for a few more seconds while
  // the real session actually spins up. Without this, the button snaps back
  // to its normal state right after the click with nothing else visible
  // happening in between, which reads as "did that even do anything?". This
  // keeps a loading state showing until the status genuinely moves on —
  // reset during render (React's recommended "adjust state on a prop
  // change" pattern) rather than in an effect, which would cost an extra
  // commit for something derivable synchronously.
  const [awaitingProgress, setAwaitingProgress] = useState(false)
  const currentState = status.data?.state
  const [lastObservedState, setLastObservedState] = useState(currentState)
  if (currentState !== lastObservedState) {
    setLastObservedState(currentState)
    if (currentState && currentState !== 'disconnected') {
      setAwaitingProgress(false)
    }
  }

  // Mirrors the `awaitingProgress`/`lastObservedState` pattern above, for the
  // server-reported discovery flag: this covers a page that reloaded while
  // `POST /whatsapp/discover-and-sync` was still running server-side (see
  // `whatsapp_status/router.py`) — this page instance never itself started
  // that mutation, so `discoverAndSync.isPending`/its own `onSuccess` can't
  // fire the navigate. Observing the polled flag flip from `true` to `false`
  // is the only way this instance finds out discovery just finished.
  const discoveryInProgress = status.data?.discoveryInProgress ?? false
  const [lastDiscoveryInProgress, setLastDiscoveryInProgress] = useState(discoveryInProgress)
  if (discoveryInProgress !== lastDiscoveryInProgress) {
    setLastDiscoveryInProgress(discoveryInProgress)
    if (lastDiscoveryInProgress && !discoveryInProgress) {
      // This instance never called `useDiscoverAndSync` itself, so its
      // `onSuccess` (which invalidates `communityKeys.all`) never ran —
      // without this, `indexRoute`'s `beforeLoad` could serve a cached,
      // pre-discovery (possibly empty) communities list for up to
      // `staleTime`, landing back on "No communities yet" right after
      // discovery actually found some.
      void queryClient.invalidateQueries({ queryKey: communityKeys.all })
      void queryClient.invalidateQueries({ queryKey: whatsappKeys.status })
      void navigate({ to: '/' })
    }
  }

  const connectError =
    connect.error instanceof ApiError ? connect.error.message : connect.error ? 'Something went wrong. Please try again.' : null
  const discoverError =
    discoverAndSync.error instanceof ApiError
      ? discoverAndSync.error.message
      : discoverAndSync.error
        ? 'Something went wrong. Please try again.'
        : null

  function handleConnect() {
    setAwaitingProgress(true)
    connect.mutate(undefined, {
      onError: () => setAwaitingProgress(false),
    })
  }

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
              onConnect={handleConnect}
              connectPending={connect.isPending || awaitingProgress}
              connectError={connectError}
              onDiscover={handleDiscover}
              discoverPending={discoverAndSync.isPending || discoveryInProgress}
              discoverError={discoverError}
              isViewer={isViewer}
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
  isViewer: boolean
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
  isViewer,
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
        <Button className="w-full gap-2" onClick={onConnect} disabled={connectPending || isViewer}>
          {connectPending ? <Loader2 className="size-4 animate-spin" /> : null}
          {connectPending ? 'Starting session…' : 'Connect WhatsApp'}
        </Button>
        {connectPending ? (
          <p className="text-center text-xs text-muted-foreground">
            This can take up to a minute before the QR code shows up.
          </p>
        ) : null}
        {isViewer ? (
          <p className="text-center text-sm text-muted-foreground">Your role doesn't have access to this.</p>
        ) : null}
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
      <Button className="w-full gap-2" onClick={onDiscover} disabled={discoverPending || isViewer}>
        {discoverPending ? <Loader2 className="size-4 animate-spin" /> : null}
        {discoverPending ? 'Discovering…' : 'Discover communities'}
      </Button>
      {discoverPending ? (
        <p className="text-center text-xs text-muted-foreground">
          This can take a few minutes for communities with many groups or members — please keep this page open.
        </p>
      ) : null}
      {isViewer ? (
        <p className="text-center text-sm text-muted-foreground">Your role doesn't have access to this.</p>
      ) : null}
    </div>
  )
}
