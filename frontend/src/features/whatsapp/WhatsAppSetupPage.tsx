import { useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Loader2, MessageCircle } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { communityKeys } from '@/features/communities/queries'
import { useSession } from '@/features/auth/queries'
import { useConnectWhatsApp, useDiscoverAndSync, useWhatsAppStatus, whatsappKeys } from './queries'
import type { DiscoverAndSyncResult, WhatsAppConnectionState } from './types'

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

  // Holds the last `discover-and-sync` result so it can actually be shown
  // (counts, hidden-non-admin communities, per-community failures) instead
  // of navigating away the instant the request succeeds — see
  // `DiscoverResultBody` below. `null` means "nothing to show yet".
  const [discoverResult, setDiscoverResult] = useState<DiscoverAndSyncResult | null>(null)

  // Mirrors the `awaitingProgress`/`lastObservedState` pattern above, for the
  // server-reported discovery flag: this covers a page that reloaded while
  // `POST /whatsapp/discover-and-sync` was still running server-side (see
  // `whatsapp_status/router.py`) — this page instance never itself started
  // that mutation, so it never gets a `discoverResult` to show. Falling
  // back to navigating straight to `/` is the best this instance can do;
  // skipped whenever `discoverResult` is already set, so it can't yank the
  // results screen away out from under someone who's reading it.
  const discoveryInProgress = status.data?.discoveryInProgress ?? false
  const [lastDiscoveryInProgress, setLastDiscoveryInProgress] = useState(discoveryInProgress)
  if (discoveryInProgress !== lastDiscoveryInProgress) {
    setLastDiscoveryInProgress(discoveryInProgress)
    if (lastDiscoveryInProgress && !discoveryInProgress && discoverResult === null) {
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
      onSuccess: (result) => setDiscoverResult(result),
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

          {!status.isPending && status.data && discoverResult ? (
            <DiscoverResultBody
              result={discoverResult}
              onDiscoverAgain={() => {
                setDiscoverResult(null)
                handleDiscover()
              }}
              onContinue={() => {
                void navigate({ to: '/' })
              }}
              discoverPending={discoverAndSync.isPending}
            />
          ) : null}

          {!status.isPending && status.data && !discoverResult ? (
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

interface DiscoverResultBodyProps {
  result: DiscoverAndSyncResult
  onDiscoverAgain: () => void
  onContinue: () => void
  discoverPending: boolean
}

/** Shown right after `discover-and-sync` finishes, replacing what used to
 * be an immediate, silent navigate to `/` — the whole point is that a
 * newly-synced community never just vanishes without explanation: this is
 * the one place that says, honestly, what was found, what's hidden (and
 * why), and what failed (and why). */
function DiscoverResultBody({ result, onDiscoverAgain, onContinue, discoverPending }: DiscoverResultBodyProps) {
  const hidden = result.communities.filter((c) => result.hiddenNonAdminWaIds.includes(c.waId))
  const visibleCount = result.communities.length - hidden.length

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-2 text-sm">
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" />
        <p>
          Found <strong>{result.communities.length}</strong> {result.communities.length === 1 ? 'community' : 'communities'}
          {result.communities.length > 0 ? (
            <>
              {' '}— <strong>{visibleCount}</strong> will show up on your dashboard.
            </>
          ) : (
            '.'
          )}
        </p>
      </div>

      {hidden.length > 0 ? (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div>
            <p>
              {hidden.length} {hidden.length === 1 ? 'community is' : 'communities are'} hidden because this
              WhatsApp number isn't an admin there:
            </p>
            <ul className="mt-1 list-inside list-disc">
              {hidden.map((c) => (
                <li key={c.waId}>{c.name}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {result.failed.length > 0 ? (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div>
            <p>{result.failed.length} {result.failed.length === 1 ? 'community' : 'communities'} failed to sync:</p>
            <ul className="mt-1 list-inside list-disc">
              {result.failed.map((f) => (
                <li key={f.waId}>
                  {f.name} — {f.reason}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        <Button className="w-full" onClick={onContinue}>
          Continue to dashboard
        </Button>
        {result.failed.length > 0 ? (
          <Button variant="outline" className="w-full gap-2" onClick={onDiscoverAgain} disabled={discoverPending}>
            {discoverPending ? <Loader2 className="size-4 animate-spin" /> : null}
            {discoverPending ? 'Discovering…' : 'Try again for the failed ones'}
          </Button>
        ) : null}
      </div>
    </div>
  )
}
