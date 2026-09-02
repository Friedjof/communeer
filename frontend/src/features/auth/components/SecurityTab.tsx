import { Link } from '@tanstack/react-router'
import { MessageCircle, MessageCircleOff, ShieldCheck, ShieldOff } from 'lucide-react'
import { REGEXP_ONLY_DIGITS } from 'input-otp'
import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { isTotpRequired } from '../types'
import {
  useDisableTotp,
  useDisableWhatsAppOtp,
  useEnableWhatsAppOtp,
  useRegenerateRecoveryCodes,
  useSession,
  useSetupWhatsAppOtp,
} from '../queries'

function apiErrorMessage(error: unknown): string | null {
  if (error instanceof ApiError) return error.message
  if (error) return 'Something went wrong. Please try again.'
  return null
}

function DisableTotpDialog() {
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const disable = useDisableTotp()

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setPassword('')
          disable.reset()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Disable
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Disable two-factor authentication?</DialogTitle>
          <DialogDescription>Confirm with your password. Your recovery codes will stop working too.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="disable-totp-password" className="text-sm font-medium">
            Password
          </label>
          <Input
            id="disable-totp-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {apiErrorMessage(disable.error) ? (
            <p role="alert" className="text-sm text-destructive">
              {apiErrorMessage(disable.error)}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={disable.isPending || password.length === 0}
            onClick={() => {
              disable.mutate(password, { onSuccess: () => setOpen(false) })
            }}
          >
            {disable.isPending ? 'Disabling…' : 'Disable'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RegenerateRecoveryCodesDialog() {
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const regenerate = useRegenerateRecoveryCodes()

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setPassword('')
          regenerate.reset()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Regenerate recovery codes
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Regenerate recovery codes</DialogTitle>
          <DialogDescription>
            Confirm with your password. Your existing recovery codes stop working immediately.
          </DialogDescription>
        </DialogHeader>
        {regenerate.data ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              Save these somewhere safe — they won't be shown again.
            </p>
            <div className="grid grid-cols-2 gap-1.5 rounded-lg border bg-muted/30 p-3 font-mono text-sm">
              {regenerate.data.recoveryCodes.map((code) => (
                <span key={code}>{code}</span>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="regenerate-codes-password" className="text-sm font-medium">
              Password
            </label>
            <Input
              id="regenerate-codes-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {apiErrorMessage(regenerate.error) ? (
              <p role="alert" className="text-sm text-destructive">
                {apiErrorMessage(regenerate.error)}
              </p>
            ) : null}
          </div>
        )}
        <DialogFooter>
          {regenerate.data ? (
            <Button onClick={() => setOpen(false)}>Done</Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button disabled={regenerate.isPending || password.length === 0} onClick={() => regenerate.mutate(password)}>
                {regenerate.isPending ? 'Generating…' : 'Regenerate'}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DisableWhatsAppOtpDialog() {
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const disable = useDisableWhatsAppOtp()

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setPassword('')
          disable.reset()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Disable
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Disable WhatsApp login codes?</DialogTitle>
          <DialogDescription>Confirm with your password.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="disable-whatsapp-otp-password" className="text-sm font-medium">
            Password
          </label>
          <Input
            id="disable-whatsapp-otp-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {apiErrorMessage(disable.error) ? (
            <p role="alert" className="text-sm text-destructive">
              {apiErrorMessage(disable.error)}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={disable.isPending || password.length === 0}
            onClick={() => {
              disable.mutate(password, { onSuccess: () => setOpen(false) })
            }}
          >
            {disable.isPending ? 'Disabling…' : 'Disable'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function SetupWhatsAppOtpDialog() {
  const [open, setOpen] = useState(false)
  const [phoneNumber, setPhoneNumber] = useState('')
  const [code, setCode] = useState('')
  const [phoneWaId, setPhoneWaId] = useState<string | null>(null)
  const setup = useSetupWhatsAppOtp()
  const enable = useEnableWhatsAppOtp()

  function reset() {
    setPhoneNumber('')
    setCode('')
    setPhoneWaId(null)
    setup.reset()
    enable.reset()
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Set up WhatsApp login codes
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>WhatsApp login codes</DialogTitle>
          <DialogDescription>
            {enable.data
              ? 'WhatsApp login codes are enabled.'
              : phoneWaId
                ? 'Enter the code we sent to your WhatsApp.'
                : 'Enter your WhatsApp number to receive a verification code.'}
          </DialogDescription>
        </DialogHeader>

        {enable.data ? (
          enable.data.recoveryCodes ? (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">
                Save these somewhere safe — they won't be shown again.
              </p>
              <div className="grid grid-cols-2 gap-1.5 rounded-lg border bg-muted/30 p-3 font-mono text-sm">
                {enable.data.recoveryCodes.map((recoveryCode) => (
                  <span key={recoveryCode}>{recoveryCode}</span>
                ))}
              </div>
            </div>
          ) : null
        ) : phoneWaId ? (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="whatsapp-otp-code" className="text-sm font-medium">
              6-digit code
            </label>
            <InputOTP
              id="whatsapp-otp-code"
              autoFocus
              maxLength={6}
              pattern={REGEXP_ONLY_DIGITS}
              value={code}
              onChange={setCode}
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
            {apiErrorMessage(enable.error) ? (
              <p role="alert" className="text-sm text-destructive">
                {apiErrorMessage(enable.error)}
              </p>
            ) : null}
            <button
              type="button"
              className="mt-1 w-fit text-sm text-muted-foreground underline-offset-4 hover:underline"
              disabled={setup.isPending}
              onClick={() => setup.mutate(phoneNumber, { onSuccess: (result) => setPhoneWaId(result.phoneWaId) })}
            >
              Resend code
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="whatsapp-otp-phone" className="text-sm font-medium">
              WhatsApp number
            </label>
            <Input
              id="whatsapp-otp-phone"
              type="tel"
              autoFocus
              placeholder="+49 151 23456789"
              value={phoneNumber}
              onChange={(event) => setPhoneNumber(event.target.value)}
            />
            {apiErrorMessage(setup.error) ? (
              <p role="alert" className="text-sm text-destructive">
                {apiErrorMessage(setup.error)}
              </p>
            ) : null}
          </div>
        )}

        <DialogFooter>
          {enable.data ? (
            <Button onClick={() => setOpen(false)}>Done</Button>
          ) : phoneWaId ? (
            <>
              <Button variant="outline" onClick={() => setPhoneWaId(null)}>
                Back
              </Button>
              <Button disabled={enable.isPending || code.length === 0} onClick={() => enable.mutate(code)}>
                {enable.isPending ? 'Verifying…' : 'Verify'}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button
                disabled={setup.isPending || phoneNumber.length === 0}
                onClick={() => setup.mutate(phoneNumber, { onSuccess: (result) => setPhoneWaId(result.phoneWaId) })}
              >
                {setup.isPending ? 'Sending…' : 'Send code'}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function SecurityTab() {
  const session = useSession()

  if (!session.data) {
    return null
  }

  const { role, totpEnabled, whatsappOtpEnabled } = session.data
  const required = isTotpRequired(role)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-4 rounded-lg border p-4">
        <div className="flex items-center gap-3">
          {totpEnabled ? (
            <ShieldCheck className="size-5 text-success" />
          ) : (
            <ShieldOff className="size-5 text-muted-foreground" />
          )}
          <div>
            <p className="font-medium">Two-factor authentication</p>
            <p className="text-sm text-muted-foreground">
              {totpEnabled
                ? 'A code from your authenticator app is required on every sign-in.'
                : required && !whatsappOtpEnabled
                  ? 'Required for your role — set it up to keep using Communeer.'
                  : 'Adds a code from an authenticator app on top of your password.'}
            </p>
          </div>
          <Badge variant={totpEnabled ? 'default' : 'secondary'} className="ml-auto">
            {totpEnabled ? 'Enabled' : 'Not enabled'}
          </Badge>
        </div>
        {totpEnabled ? (
          <div className="flex flex-wrap gap-2">
            <RegenerateRecoveryCodesDialog />
            <DisableTotpDialog />
          </div>
        ) : (
          <Button asChild variant="outline" className="w-fit">
            <Link to="/setup/2fa">Set up two-factor authentication</Link>
          </Button>
        )}
      </div>

      <div className="flex flex-col gap-4 rounded-lg border p-4">
        <div className="flex items-center gap-3">
          {whatsappOtpEnabled ? (
            <MessageCircle className="size-5 text-success" />
          ) : (
            <MessageCircleOff className="size-5 text-muted-foreground" />
          )}
          <div>
            <p className="font-medium">WhatsApp login codes</p>
            <p className="text-sm text-muted-foreground">
              {whatsappOtpEnabled
                ? 'A code sent to your WhatsApp can be used to sign in instead of your authenticator app.'
                : 'An alternative to your authenticator app — sign in with a code sent to your own WhatsApp number.'}
            </p>
          </div>
          <Badge variant={whatsappOtpEnabled ? 'default' : 'secondary'} className="ml-auto">
            {whatsappOtpEnabled ? 'Enabled' : 'Not enabled'}
          </Badge>
        </div>
        {whatsappOtpEnabled ? (
          <div className="flex flex-wrap gap-2">
            <DisableWhatsAppOtpDialog />
          </div>
        ) : totpEnabled ? (
          <div className="flex flex-wrap gap-2">
            <SetupWhatsAppOtpDialog />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Set up two-factor authentication above first.
          </p>
        )}
      </div>
    </div>
  )
}
