import { useNavigate } from '@tanstack/react-router'
import { REGEXP_ONLY_DIGITS } from 'input-otp'
import { type FormEvent, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import {
  useLogin,
  useRequestLoginWhatsappOtp,
  useVerifyLoginTotp,
  useVerifyLoginWhatsappOtp,
} from './queries'

type Stage = 'credentials' | 'choose-method' | 'totp' | 'whatsapp'

function errorMessage(error: unknown): string | null {
  if (!error) return null
  return error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
}

/** A 6-digit-code entry switches between the "6 separate boxes" OTP UI and a
 * plain text field once the recovery-code toggle is on (recovery codes are
 * 32-char alphanumeric, not a fixed 6 digits) — shared by the TOTP and
 * WhatsApp-OTP stages below, which otherwise duplicate this exact toggle. */
function CodeField({
  id,
  useRecoveryCode,
  code,
  onCodeChange,
}: {
  id: string
  useRecoveryCode: boolean
  code: string
  onCodeChange: (value: string) => void
}) {
  if (useRecoveryCode) {
    return (
      <Input
        id={id}
        name="code"
        inputMode="text"
        autoComplete="one-time-code"
        autoFocus
        maxLength={32}
        value={code}
        onChange={(event) => onCodeChange(event.target.value)}
        required
      />
    )
  }
  return (
    <InputOTP
      id={id}
      name="code"
      autoComplete="one-time-code"
      autoFocus
      maxLength={6}
      pattern={REGEXP_ONLY_DIGITS}
      value={code}
      onChange={onCodeChange}
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
  )
}

export function LoginPage() {
  const navigate = useNavigate()
  const login = useLogin()
  const verifyTotp = useVerifyLoginTotp()
  const requestWhatsappOtp = useRequestLoginWhatsappOtp()
  const verifyWhatsappOtp = useVerifyLoginWhatsappOtp()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [useRecoveryCode, setUseRecoveryCode] = useState(false)
  const [whatsappCodeSent, setWhatsappCodeSent] = useState(false)
  const [stage, setStage] = useState<Stage>('credentials')

  function goToHome() {
    void navigate({ to: '/' })
  }

  function handleCredentialsSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    login.mutate(
      { username, password },
      {
        onSuccess: (result) => {
          if (!result.requiresTotp) {
            goToHome()
            return
          }
          // `totpEnabled`/`whatsappOtpEnabled` are `undefined` for a mocked
          // `{ requiresTotp: true }` payload with no factor fields (older
          // shape) — falls through to the `totp` stage, matching this
          // page's pre-WhatsApp-OTP behavior exactly.
          if (result.whatsappOtpEnabled && result.totpEnabled) {
            setStage('choose-method')
          } else if (result.whatsappOtpEnabled) {
            setStage('whatsapp')
          } else {
            setStage('totp')
          }
        },
      },
    )
  }

  function handleTotpSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    verifyTotp.mutate(code, { onSuccess: goToHome })
  }

  function handleWhatsappVerifySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    verifyWhatsappOtp.mutate(code, { onSuccess: goToHome })
  }

  const credentialsError = errorMessage(login.error)
  const totpError = errorMessage(verifyTotp.error)
  const whatsappRequestError = errorMessage(requestWhatsappOtp.error)
  const whatsappVerifyError = errorMessage(verifyWhatsappOtp.error)

  const descriptionByStage: Record<Stage, string> = {
    credentials: 'Sign in to manage your WhatsApp communities.',
    'choose-method': 'Choose how to verify it’s you.',
    totp: 'Enter the code from your authenticator app.',
    whatsapp: 'Verify with a code sent to your WhatsApp.',
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <img src="/logo.png" alt="" className="mb-2 size-12" />
          <CardTitle className="text-xl">Communeer</CardTitle>
          <CardDescription>{descriptionByStage[stage]}</CardDescription>
        </CardHeader>
        <CardContent>
          {stage === 'credentials' ? (
            <form className="flex flex-col gap-4" onSubmit={handleCredentialsSubmit}>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="username" className="text-sm font-medium">
                  Username
                </label>
                <Input
                  id="username"
                  name="username"
                  autoComplete="username"
                  autoFocus
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="text-sm font-medium">
                  Password
                </label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
              </div>
              {credentialsError ? (
                <p role="alert" className="text-sm text-destructive">
                  {credentialsError}
                </p>
              ) : null}
              <Button type="submit" className="mt-2 w-full" disabled={login.isPending}>
                {login.isPending ? 'Signing in…' : 'Sign in'}
              </Button>
            </form>
          ) : null}

          {stage === 'choose-method' ? (
            <div className="flex flex-col gap-3">
              <Button variant="outline" className="w-full" onClick={() => setStage('totp')}>
                Use authenticator app code
              </Button>
              <Button variant="outline" className="w-full" onClick={() => setStage('whatsapp')}>
                Use a WhatsApp code
              </Button>
            </div>
          ) : null}

          {stage === 'totp' ? (
            <form className="flex flex-col gap-4" onSubmit={handleTotpSubmit}>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="totp-code" className="text-sm font-medium">
                  {useRecoveryCode ? 'Recovery code' : '6-digit code'}
                </label>
                <CodeField id="totp-code" useRecoveryCode={useRecoveryCode} code={code} onCodeChange={setCode} />
              </div>
              {totpError ? (
                <p role="alert" className="text-sm text-destructive">
                  {totpError}
                </p>
              ) : null}
              <Button type="submit" className="mt-2 w-full" disabled={verifyTotp.isPending}>
                {verifyTotp.isPending ? 'Verifying…' : 'Verify'}
              </Button>
              <button
                type="button"
                className="text-sm text-muted-foreground underline-offset-4 hover:underline"
                onClick={() => {
                  setUseRecoveryCode((v) => !v)
                  setCode('')
                }}
              >
                {useRecoveryCode ? 'Use an authenticator code instead' : 'Use a recovery code instead'}
              </button>
            </form>
          ) : null}

          {stage === 'whatsapp' ? (
            !whatsappCodeSent ? (
              <div className="flex flex-col gap-4">
                {whatsappRequestError ? (
                  <p role="alert" className="text-sm text-destructive">
                    {whatsappRequestError}
                  </p>
                ) : null}
                <Button
                  type="button"
                  className="w-full"
                  disabled={requestWhatsappOtp.isPending}
                  onClick={() =>
                    requestWhatsappOtp.mutate(undefined, { onSuccess: () => setWhatsappCodeSent(true) })
                  }
                >
                  {requestWhatsappOtp.isPending ? 'Sending…' : 'Send me a code via WhatsApp'}
                </Button>
              </div>
            ) : (
              <form className="flex flex-col gap-4" onSubmit={handleWhatsappVerifySubmit}>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="whatsapp-code" className="text-sm font-medium">
                    {useRecoveryCode ? 'Recovery code' : 'Code from WhatsApp'}
                  </label>
                  <CodeField id="whatsapp-code" useRecoveryCode={useRecoveryCode} code={code} onCodeChange={setCode} />
                </div>
                {whatsappVerifyError ? (
                  <p role="alert" className="text-sm text-destructive">
                    {whatsappVerifyError}
                  </p>
                ) : null}
                <Button type="submit" className="mt-2 w-full" disabled={verifyWhatsappOtp.isPending}>
                  {verifyWhatsappOtp.isPending ? 'Verifying…' : 'Verify'}
                </Button>
                <div className="flex items-center justify-between text-sm">
                  <button
                    type="button"
                    className="text-muted-foreground underline-offset-4 hover:underline"
                    onClick={() => {
                      setUseRecoveryCode((v) => !v)
                      setCode('')
                    }}
                  >
                    {useRecoveryCode ? 'Use a WhatsApp code instead' : 'Use a recovery code instead'}
                  </button>
                  <button
                    type="button"
                    className="text-muted-foreground underline-offset-4 hover:underline disabled:pointer-events-none disabled:opacity-50"
                    disabled={requestWhatsappOtp.isPending}
                    onClick={() => requestWhatsappOtp.mutate(undefined)}
                  >
                    Resend code
                  </button>
                </div>
              </form>
            )
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
