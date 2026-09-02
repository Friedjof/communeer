import { useNavigate } from '@tanstack/react-router'
import { Check, CheckCircle2, Copy } from 'lucide-react'
import { REGEXP_ONLY_DIGITS } from 'input-otp'
import QRCode from 'qrcode'
import { type FormEvent, useEffect, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { HelpTooltip } from '@/components/ui/help-tooltip'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { Skeleton } from '@/components/ui/skeleton'
import { useEnableTotp, useSetupTotp } from './queries'

/** Mandatory for owner/admin (see `app/router.tsx`'s `beforeLoad` redirect
 * and the backend's `deps.get_current_user` 428 gate) — a fresh owner/admin
 * account lands here before it can do anything else. Mirrors
 * `WhatsAppSetupPage.tsx`'s "blocking setup screen" structure. */
export function TotpSetupPage() {
  const navigate = useNavigate()
  const setup = useSetupTotp()
  const enable = useEnableTotp()
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [savedCodesConfirmed, setSavedCodesConfirmed] = useState(false)
  const [secretCopied, setSecretCopied] = useState(false)

  async function handleCopySecret(secret: string) {
    await navigator.clipboard.writeText(secret)
    setSecretCopied(true)
    setTimeout(() => setSecretCopied(false), 2000)
  }

  useEffect(() => {
    setup.mutate()
    // Only ever fetched once per page visit — a fresh secret every render
    // would invalidate whatever the user already scanned.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!setup.data) return
    let cancelled = false
    QRCode.toDataURL(setup.data.otpauthUri, { width: 224, margin: 1 }).then((url) => {
      if (!cancelled) setQrDataUrl(url)
    })
    return () => {
      cancelled = true
    }
  }, [setup.data])

  const secret = setup.data?.secret
  const setupError =
    setup.error instanceof ApiError ? setup.error.message : setup.error ? 'Something went wrong. Please try again.' : null
  const enableError =
    enable.error instanceof ApiError ? enable.error.message : enable.error ? 'Something went wrong. Please try again.' : null

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    enable.mutate(code, {
      onSuccess: (result) => setRecoveryCodes(result.recoveryCodes),
    })
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <img src="/logo.png" alt="" className="mb-2 size-12" />
          <CardTitle className="text-xl">Set up two-factor authentication</CardTitle>
          <CardDescription>
            Required for your role — protects this account with a code from an authenticator app, on top of your
            password.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {recoveryCodes ? (
            <RecoveryCodesStep
              codes={recoveryCodes}
              confirmed={savedCodesConfirmed}
              onConfirmedChange={setSavedCodesConfirmed}
              onContinue={() => void navigate({ to: '/' })}
            />
          ) : (
            <div className="flex flex-col gap-4">
              {setupError ? (
                <p role="alert" className="text-center text-sm text-destructive">
                  {setupError}
                </p>
              ) : null}

              <p className="text-center text-sm text-muted-foreground">
                Scan this with an authenticator app (e.g. Google Authenticator, Authy, 1Password).
              </p>
              {qrDataUrl ? (
                <img src={qrDataUrl} alt="Two-factor authentication QR code" className="mx-auto size-56 rounded-md border" />
              ) : (
                <Skeleton className="mx-auto size-56 rounded-md" />
              )}
              {secret ? (
                <div className="flex flex-col items-center gap-1.5">
                  <p className="text-center text-xs text-muted-foreground">Can't scan? Enter this code manually:</p>
                  <div className="flex w-full items-center gap-1 rounded-lg border bg-muted/30 p-2">
                    <p className="flex-1 break-all text-center font-mono text-xs">{secret}</p>
                    <HelpTooltip content="Copy code to clipboard">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Copy code"
                        onClick={() => handleCopySecret(secret)}
                      >
                        {secretCopied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
                      </Button>
                    </HelpTooltip>
                  </div>
                </div>
              ) : null}

              <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
                <div className="flex flex-col items-center gap-1.5">
                  <label htmlFor="totp-code" className="text-sm font-medium">
                    6-digit code
                  </label>
                  <InputOTP
                    id="totp-code"
                    name="code"
                    autoComplete="one-time-code"
                    autoFocus
                    maxLength={6}
                    pattern={REGEXP_ONLY_DIGITS}
                    value={code}
                    onChange={setCode}
                    required
                  >
                    <InputOTPGroup>
                      <InputOTPSlot index={0} />
                      <InputOTPSlot index={1} />
                      <InputOTPSlot index={2} />
                      <InputOTPSlot index={3} />
                      <InputOTPSlot index={4} />
                      <InputOTPSlot index={5} />
                    </InputOTPGroup>
                  </InputOTP>
                </div>
                {enableError ? (
                  <p role="alert" className="text-sm text-destructive">
                    {enableError}
                  </p>
                ) : null}
                <Button type="submit" className="w-full" disabled={enable.isPending || !setup.data}>
                  {enable.isPending ? 'Confirming…' : 'Confirm and enable'}
                </Button>
              </form>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function RecoveryCodesStep({
  codes,
  confirmed,
  onConfirmedChange,
  onContinue,
}: {
  codes: string[]
  confirmed: boolean
  onConfirmedChange: (confirmed: boolean) => void
  onContinue: () => void
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 text-success">
        <CheckCircle2 className="size-5" />
        <p className="text-sm font-medium">Two-factor authentication is enabled.</p>
      </div>
      <p className="text-sm text-muted-foreground">
        Save these recovery codes somewhere safe — each works once, to sign in if you lose access to your
        authenticator app. They won't be shown again.
      </p>
      <div className="grid grid-cols-2 gap-1.5 rounded-lg border bg-muted/30 p-3 font-mono text-sm">
        {codes.map((code) => (
          <span key={code}>{code}</span>
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox checked={confirmed} onCheckedChange={(checked) => onConfirmedChange(checked === true)} />
        I've saved these recovery codes
      </label>
      <Button className="w-full" disabled={!confirmed} onClick={onContinue}>
        Continue to Communeer
      </Button>
    </div>
  )
}
