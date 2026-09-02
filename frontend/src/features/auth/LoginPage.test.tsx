import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from './LoginPage'

const {
  useLoginMock,
  useVerifyLoginTotpMock,
  useRequestLoginWhatsappOtpMock,
  useVerifyLoginWhatsappOtpMock,
  useNavigateMock,
} = vi.hoisted(() => ({
  useLoginMock: vi.fn(),
  useVerifyLoginTotpMock: vi.fn(),
  useRequestLoginWhatsappOtpMock: vi.fn(),
  useVerifyLoginWhatsappOtpMock: vi.fn(),
  useNavigateMock: vi.fn(),
}))

vi.mock('./queries', () => ({
  useLogin: useLoginMock,
  useVerifyLoginTotp: useVerifyLoginTotpMock,
  useRequestLoginWhatsappOtp: useRequestLoginWhatsappOtpMock,
  useVerifyLoginWhatsappOtp: useVerifyLoginWhatsappOtpMock,
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: useNavigateMock,
}))

describe('LoginPage', () => {
  beforeEach(() => {
    // Neither of these is exercised by the TOTP-only/no-2FA tests below —
    // default them to inert mocks so those tests don't need to know about
    // WhatsApp-OTP at all.
    useRequestLoginWhatsappOtpMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
    useVerifyLoginWhatsappOtpMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
  })

  it('switches to the code-entry stage when the password step requires TOTP', async () => {
    const navigate = vi.fn()
    useNavigateMock.mockReturnValue(navigate)
    const loginMutate = vi.fn((_credentials, options) => {
      options?.onSuccess?.({ requiresTotp: true, totpEnabled: true, whatsappOtpEnabled: false })
    })
    useLoginMock.mockReturnValue({ mutate: loginMutate, isPending: false, error: null })
    useVerifyLoginTotpMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })

    render(<LoginPage />)

    await userEvent.type(screen.getByLabelText(/username/i), 'admin')
    await userEvent.type(screen.getByLabelText(/password/i), 'changeme123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(loginMutate).toHaveBeenCalledWith(
      { username: 'admin', password: 'changeme123' },
      expect.anything(),
    )
    expect(screen.getByLabelText(/6-digit code/i)).toBeInTheDocument()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('logs straight in without a TOTP step when the account has none enabled', async () => {
    const navigate = vi.fn()
    useNavigateMock.mockReturnValue(navigate)
    const loginMutate = vi.fn((_credentials, options) => {
      options?.onSuccess?.({
        requiresTotp: false,
        user: { id: '1', username: 'admin', role: 'viewer', totpEnabled: false, whatsappOtpEnabled: false },
      })
    })
    useLoginMock.mockReturnValue({ mutate: loginMutate, isPending: false, error: null })
    useVerifyLoginTotpMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })

    render(<LoginPage />)

    await userEvent.type(screen.getByLabelText(/username/i), 'viewer')
    await userEvent.type(screen.getByLabelText(/password/i), 'viewer-password-123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(navigate).toHaveBeenCalledWith({ to: '/' })
    expect(screen.queryByLabelText(/6-digit code/i)).not.toBeInTheDocument()
  })

  it('completes login after a valid code and navigates home', async () => {
    const navigate = vi.fn()
    useNavigateMock.mockReturnValue(navigate)
    useLoginMock.mockReturnValue({
      mutate: vi.fn((_credentials, options) =>
        options?.onSuccess?.({ requiresTotp: true, totpEnabled: true, whatsappOtpEnabled: false }),
      ),
      isPending: false,
      error: null,
    })
    const verifyMutate = vi.fn((_code, options) => {
      options?.onSuccess?.()
    })
    useVerifyLoginTotpMock.mockReturnValue({ mutate: verifyMutate, isPending: false, error: null })

    render(<LoginPage />)

    await userEvent.type(screen.getByLabelText(/username/i), 'admin')
    await userEvent.type(screen.getByLabelText(/password/i), 'changeme123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await userEvent.type(screen.getByLabelText(/6-digit code/i), '123456')
    await userEvent.click(screen.getByRole('button', { name: /verify/i }))

    expect(verifyMutate).toHaveBeenCalledWith('123456', expect.anything())
    expect(navigate).toHaveBeenCalledWith({ to: '/' })
  })

  it('offers a method choice when both TOTP and WhatsApp-OTP are enabled', async () => {
    useNavigateMock.mockReturnValue(vi.fn())
    const loginMutate = vi.fn((_credentials, options) => {
      options?.onSuccess?.({ requiresTotp: true, totpEnabled: true, whatsappOtpEnabled: true })
    })
    useLoginMock.mockReturnValue({ mutate: loginMutate, isPending: false, error: null })
    useVerifyLoginTotpMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })

    render(<LoginPage />)

    await userEvent.type(screen.getByLabelText(/username/i), 'admin')
    await userEvent.type(screen.getByLabelText(/password/i), 'changeme123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(screen.getByRole('button', { name: /use authenticator app code/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /use a whatsapp code/i })).toBeInTheDocument()
    expect(screen.queryByLabelText(/6-digit code/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /use authenticator app code/i }))
    expect(screen.getByLabelText(/6-digit code/i)).toBeInTheDocument()
  })

  it('goes straight to the WhatsApp send step when only WhatsApp-OTP is enabled', async () => {
    useNavigateMock.mockReturnValue(vi.fn())
    const loginMutate = vi.fn((_credentials, options) => {
      options?.onSuccess?.({ requiresTotp: true, totpEnabled: false, whatsappOtpEnabled: true })
    })
    useLoginMock.mockReturnValue({ mutate: loginMutate, isPending: false, error: null })
    const requestMutate = vi.fn((_arg, options) => {
      options?.onSuccess?.()
    })
    useRequestLoginWhatsappOtpMock.mockReturnValue({ mutate: requestMutate, isPending: false, error: null })

    render(<LoginPage />)

    await userEvent.type(screen.getByLabelText(/username/i), 'admin')
    await userEvent.type(screen.getByLabelText(/password/i), 'changeme123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    const sendButton = screen.getByRole('button', { name: /send me a code via whatsapp/i })
    expect(sendButton).toBeInTheDocument()
    await userEvent.click(sendButton)

    expect(requestMutate).toHaveBeenCalled()
    expect(screen.getByLabelText(/code from whatsapp/i)).toBeInTheDocument()
  })
})
