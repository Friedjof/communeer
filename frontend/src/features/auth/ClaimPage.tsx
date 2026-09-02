import { Link, useNavigate } from '@tanstack/react-router'
import { REGEXP_ONLY_DIGITS } from 'input-otp'
import { type FormEvent, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { useCompleteClaim, useRequestClaim } from './queries'

type Stage = 'phone' | 'code'

function errorMessage(error: unknown): string | null {
  if (!error) return null
  return error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
}

/**
 * Unauthenticated: how an auto-provisioned `group_admin` account (created
 * when a real WhatsApp group admin is synced, see backend
 * `auth/provisioning.py`) becomes usable. Two stages: request a code by
 * phone number, then use it to set a password (and optionally a username).
 * `request` always looks like a no-op success — no account-enumeration
 * oracle, see `auth/claim_service.py::request_claim` — so this page can't
 * tell the visitor whether the number matched anything; it just always
 * moves on to the code stage.
 */
export function ClaimPage() {
  const navigate = useNavigate()
  const requestClaim = useRequestClaim()
  const completeClaim = useCompleteClaim()
  const [phoneNumber, setPhoneNumber] = useState('')
  const [code, setCode] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [stage, setStage] = useState<Stage>('phone')

  function handlePhoneSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    requestClaim.mutate(phoneNumber, { onSuccess: () => setStage('code') })
  }

  function handleCompleteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    completeClaim.mutate(
      { phoneNumber, code, username: username.trim() || undefined, password },
      { onSuccess: () => void navigate({ to: '/' }) },
    )
  }

  const requestError = errorMessage(requestClaim.error)
  const completeError = errorMessage(completeClaim.error)

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <img src="/logo.png" alt="" className="mb-2 size-12" />
          <CardTitle className="text-xl">Activate your account</CardTitle>
          <CardDescription>
            {stage === 'phone'
              ? "Enter the WhatsApp number your admin account is linked to, and we'll send you a code."
              : 'Enter the code we sent you, and choose a password to finish setting up your account.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {stage === 'phone' ? (
            <form className="flex flex-col gap-4" onSubmit={handlePhoneSubmit}>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="claim-phone" className="text-sm font-medium">
                  WhatsApp number
                </label>
                <Input
                  id="claim-phone"
                  name="phoneNumber"
                  type="tel"
                  autoComplete="tel"
                  autoFocus
                  placeholder="+49 151 23456789"
                  value={phoneNumber}
                  onChange={(event) => setPhoneNumber(event.target.value)}
                  required
                />
              </div>
              {requestError ? (
                <p role="alert" className="text-sm text-destructive">
                  {requestError}
                </p>
              ) : null}
              <Button type="submit" className="mt-2 w-full" disabled={requestClaim.isPending}>
                {requestClaim.isPending ? 'Sending…' : 'Send me a code'}
              </Button>
            </form>
          ) : (
            <form className="flex flex-col gap-4" onSubmit={handleCompleteSubmit}>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="claim-code" className="text-sm font-medium">
                  Code from WhatsApp
                </label>
                <InputOTP
                  id="claim-code"
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
              <div className="flex flex-col gap-1.5">
                <label htmlFor="claim-username" className="text-sm font-medium">
                  Username <span className="font-normal text-muted-foreground">(optional)</span>
                </label>
                <Input
                  id="claim-username"
                  name="username"
                  autoComplete="username"
                  placeholder="Leave blank to keep the assigned one"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="claim-password" className="text-sm font-medium">
                  Choose a password
                </label>
                <Input
                  id="claim-password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
              </div>
              {completeError ? (
                <p role="alert" className="text-sm text-destructive">
                  {completeError}
                </p>
              ) : null}
              <Button type="submit" className="mt-2 w-full" disabled={completeClaim.isPending}>
                {completeClaim.isPending ? 'Activating…' : 'Activate account'}
              </Button>
              <button
                type="button"
                className="text-sm text-muted-foreground underline-offset-4 hover:underline"
                onClick={() => setStage('phone')}
              >
                Use a different number
              </button>
            </form>
          )}
          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link to="/login" className="underline underline-offset-4 hover:text-foreground">
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
