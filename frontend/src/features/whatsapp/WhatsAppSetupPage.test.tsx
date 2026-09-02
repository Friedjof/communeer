import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SessionUser } from '@/features/auth/types'
import { WhatsAppSetupPage } from './WhatsAppSetupPage'

const {
  useSessionMock,
  useWhatsAppStatusMock,
  useConnectWhatsAppMock,
  useDiscoverAndSyncMock,
  useNavigateMock,
  useQueryClientMock,
  invalidateQueriesMock,
} = vi.hoisted(() => ({
  useSessionMock: vi.fn(),
  useWhatsAppStatusMock: vi.fn(),
  useConnectWhatsAppMock: vi.fn(),
  useDiscoverAndSyncMock: vi.fn(),
  useNavigateMock: vi.fn(),
  useQueryClientMock: vi.fn(),
  invalidateQueriesMock: vi.fn(),
}))

vi.mock('@/features/auth/queries', () => ({
  useSession: useSessionMock,
}))

vi.mock('./queries', () => ({
  useWhatsAppStatus: useWhatsAppStatusMock,
  useConnectWhatsApp: useConnectWhatsAppMock,
  useDiscoverAndSync: useDiscoverAndSyncMock,
  whatsappKeys: { status: ['whatsapp', 'status'] },
}))

vi.mock('@/features/communities/queries', () => ({
  communityKeys: { all: ['communities'] },
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: useNavigateMock,
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: useQueryClientMock,
}))

function mockSession(role: SessionUser['role']) {
  useSessionMock.mockReturnValue({ data: { id: '1', username: 'user', role } })
}

function setup(role: SessionUser['role']) {
  mockSession(role)
  useNavigateMock.mockReturnValue(vi.fn())
  useQueryClientMock.mockReturnValue({ invalidateQueries: invalidateQueriesMock })
  useWhatsAppStatusMock.mockReturnValue({
    isPending: false,
    data: { state: 'disconnected', qrCodeDataUrl: null, detail: null, discoveryInProgress: false },
  })
  useConnectWhatsAppMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
  useDiscoverAndSyncMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
}

describe('WhatsAppSetupPage', () => {
  it('disables the Connect WhatsApp button for a viewer', () => {
    setup('viewer')
    render(<WhatsAppSetupPage />)

    expect(screen.getByRole('button', { name: /connect whatsapp/i })).toBeDisabled()
    expect(screen.getByText(/your role doesn't have access to this/i)).toBeInTheDocument()
  })

  it('enables the Connect WhatsApp button for an owner', () => {
    setup('owner')
    render(<WhatsAppSetupPage />)

    expect(screen.getByRole('button', { name: /connect whatsapp/i })).toBeEnabled()
    expect(screen.queryByText(/your role doesn't have access to this/i)).not.toBeInTheDocument()
  })

  it('disables the Discover communities button for a viewer once connected', () => {
    mockSession('viewer')
    useNavigateMock.mockReturnValue(vi.fn())
    useQueryClientMock.mockReturnValue({ invalidateQueries: invalidateQueriesMock })
    useWhatsAppStatusMock.mockReturnValue({
      isPending: false,
      data: { state: 'connected', qrCodeDataUrl: null, detail: null, discoveryInProgress: false },
    })
    useConnectWhatsAppMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
    useDiscoverAndSyncMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })

    render(<WhatsAppSetupPage />)

    expect(screen.getByRole('button', { name: /discover communities/i })).toBeDisabled()
  })

  it('enables the Discover communities button for an owner once connected', () => {
    mockSession('owner')
    useNavigateMock.mockReturnValue(vi.fn())
    useQueryClientMock.mockReturnValue({ invalidateQueries: invalidateQueriesMock })
    useWhatsAppStatusMock.mockReturnValue({
      isPending: false,
      data: { state: 'connected', qrCodeDataUrl: null, detail: null, discoveryInProgress: false },
    })
    useConnectWhatsAppMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
    useDiscoverAndSyncMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })

    render(<WhatsAppSetupPage />)

    expect(screen.getByRole('button', { name: /discover communities/i })).toBeEnabled()
  })

  it('invalidates the communities cache when a background discovery finishes', async () => {
    // Simulates a page that reloaded mid-discovery: this instance never
    // called `useDiscoverAndSync` itself, so it only learns discovery
    // finished via the polled `discoveryInProgress` flag flipping — and
    // must still invalidate the communities cache before navigating away,
    // the same way `useDiscoverAndSync`'s own `onSuccess` does.
    setup('owner')
    useWhatsAppStatusMock.mockReturnValue({
      isPending: false,
      data: { state: 'connected', qrCodeDataUrl: null, detail: null, discoveryInProgress: true },
    })

    const { rerender } = render(<WhatsAppSetupPage />)
    expect(invalidateQueriesMock).not.toHaveBeenCalled()

    useWhatsAppStatusMock.mockReturnValue({
      isPending: false,
      data: { state: 'connected', qrCodeDataUrl: null, detail: null, discoveryInProgress: false },
    })
    rerender(<WhatsAppSetupPage />)

    await waitFor(() => {
      expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['communities'] })
    })
  })

  it('shows what was found instead of navigating away immediately, and only continues on click', async () => {
    const navigateMock = vi.fn()
    mockSession('owner')
    useNavigateMock.mockReturnValue(navigateMock)
    useQueryClientMock.mockReturnValue({ invalidateQueries: invalidateQueriesMock })
    useWhatsAppStatusMock.mockReturnValue({
      isPending: false,
      data: { state: 'connected', qrCodeDataUrl: null, detail: null, discoveryInProgress: false },
    })
    useConnectWhatsAppMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
    useDiscoverAndSyncMock.mockReturnValue({
      isPending: false,
      error: null,
      mutate: (_vars: unknown, options: { onSuccess: (result: unknown) => void }) => {
        options.onSuccess({
          communities: [
            { id: '1', waId: 'a@g.us', name: 'Downtown Collective' },
            { id: '2', waId: 'b@g.us', name: 'Chess Club' },
          ],
          hiddenNonAdminWaIds: ['b@g.us'],
          failed: [{ waId: 'c@g.us', name: 'Book Club', reason: 'WhatsApp took too long to respond.' }],
        })
      },
    })

    render(<WhatsAppSetupPage />)

    await userEvent.click(screen.getByRole('button', { name: /discover communities/i }))

    expect(navigateMock).not.toHaveBeenCalled()
    expect(screen.getByText(/found/i)).toBeInTheDocument()
    expect(screen.getByText('Chess Club')).toBeInTheDocument()
    expect(screen.getByText(/isn't an admin there/i)).toBeInTheDocument()
    expect(screen.getByText(/Book Club/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /continue to dashboard/i }))
    expect(navigateMock).toHaveBeenCalledWith({ to: '/' })
  })
})
