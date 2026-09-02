import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { UsersPage } from './UsersPage'
import type { ManagedUser } from './types'

const {
  useSessionMock,
  useUsersMock,
  useUpdateUserMock,
  useCreateUserMock,
  useResetUserPasswordMock,
  useResetUserTotpMock,
  useResendClaimCodeMock,
  useApproveGroupAdminMock,
} = vi.hoisted(() => ({
  useSessionMock: vi.fn(),
  useUsersMock: vi.fn(),
  useUpdateUserMock: vi.fn(),
  useCreateUserMock: vi.fn(),
  useResetUserPasswordMock: vi.fn(),
  useResetUserTotpMock: vi.fn(),
  useResendClaimCodeMock: vi.fn(),
  useApproveGroupAdminMock: vi.fn(),
}))

vi.mock('@/features/auth/queries', () => ({
  useSession: useSessionMock,
}))

vi.mock('./queries', () => ({
  useUsers: useUsersMock,
  useUpdateUser: useUpdateUserMock,
  useCreateUser: useCreateUserMock,
  useResetUserPassword: useResetUserPasswordMock,
  useResetUserTotp: useResetUserTotpMock,
  useResendClaimCode: useResendClaimCodeMock,
  useApproveGroupAdmin: useApproveGroupAdminMock,
}))

const pendingApprovalUser: ManagedUser = {
  id: 'user-1',
  username: 'alice-admin',
  role: 'group_admin',
  isActive: true,
  createdAt: '2026-01-01T00:00:00Z',
  totpEnabled: false,
  memberId: 'member-1',
  isClaimed: false,
  isApproved: false,
  claimedAt: null,
  phoneNumberMasked: '+49 •••• 1234',
}

const approvedUnclaimedUser: ManagedUser = {
  ...pendingApprovalUser,
  id: 'user-2',
  username: 'bob-admin',
  isApproved: true,
}

function mockCommon(users: ManagedUser[]) {
  useSessionMock.mockReturnValue({ data: { id: 'owner-1', username: 'owner', role: 'owner' } })
  useUsersMock.mockReturnValue({ isPending: false, isError: false, data: users })
  useUpdateUserMock.mockReturnValue({ mutate: vi.fn(), error: null })
  useCreateUserMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() })
  useResetUserPasswordMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() })
  useResetUserTotpMock.mockReturnValue({ mutate: vi.fn(), isPending: false })
}

describe('UsersPage', () => {
  it('shows the exact claim-code message before approving, and only approves after confirming', async () => {
    mockCommon([pendingApprovalUser])
    const mutate = vi.fn()
    useResendClaimCodeMock.mockReturnValue({ mutate: vi.fn(), isPending: false, isSuccess: false, error: null })
    useApproveGroupAdminMock.mockReturnValue({ mutate, isPending: false, isSuccess: false, error: null })

    render(<UsersPage />)

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(mutate).not.toHaveBeenCalled()
    expect(screen.getByText(/Communeer-Anmeldecode/)).toBeInTheDocument()
    expect(screen.getByText(/\+49 •••• 1234/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Approve & send' }))
    expect(mutate).toHaveBeenCalledWith('user-1', expect.anything())
  })

  it('shows the exact claim-code message before resending, and only resends after confirming', async () => {
    mockCommon([approvedUnclaimedUser])
    const mutate = vi.fn()
    useResendClaimCodeMock.mockReturnValue({ mutate, isPending: false, isSuccess: false, error: null })
    useApproveGroupAdminMock.mockReturnValue({ mutate: vi.fn(), isPending: false, isSuccess: false, error: null })

    render(<UsersPage />)

    await userEvent.click(screen.getByRole('button', { name: 'Resend claim code' }))
    expect(mutate).not.toHaveBeenCalled()
    expect(screen.getByText(/Communeer-Anmeldecode/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(mutate).toHaveBeenCalledWith('user-2', expect.anything())
  })
})
