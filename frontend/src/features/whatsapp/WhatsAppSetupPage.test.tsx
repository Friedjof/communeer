import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { SessionUser } from '@/features/auth/types'
import { WhatsAppSetupPage } from './WhatsAppSetupPage'

const { useSessionMock, useWhatsAppStatusMock, useConnectWhatsAppMock, useDiscoverAndSyncMock, useNavigateMock } =
  vi.hoisted(() => ({
    useSessionMock: vi.fn(),
    useWhatsAppStatusMock: vi.fn(),
    useConnectWhatsAppMock: vi.fn(),
    useDiscoverAndSyncMock: vi.fn(),
    useNavigateMock: vi.fn(),
  }))

vi.mock('@/features/auth/queries', () => ({
  useSession: useSessionMock,
}))

vi.mock('./queries', () => ({
  useWhatsAppStatus: useWhatsAppStatusMock,
  useConnectWhatsApp: useConnectWhatsAppMock,
  useDiscoverAndSync: useDiscoverAndSyncMock,
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: useNavigateMock,
}))

function mockSession(role: SessionUser['role']) {
  useSessionMock.mockReturnValue({ data: { id: '1', username: 'user', role } })
}

function setup(role: SessionUser['role']) {
  mockSession(role)
  useNavigateMock.mockReturnValue(vi.fn())
  useWhatsAppStatusMock.mockReturnValue({
    isPending: false,
    data: { state: 'disconnected', qrCodeDataUrl: null, detail: null },
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
    useWhatsAppStatusMock.mockReturnValue({
      isPending: false,
      data: { state: 'connected', qrCodeDataUrl: null, detail: null },
    })
    useConnectWhatsAppMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
    useDiscoverAndSyncMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })

    render(<WhatsAppSetupPage />)

    expect(screen.getByRole('button', { name: /discover communities/i })).toBeDisabled()
  })

  it('enables the Discover communities button for an owner once connected', () => {
    mockSession('owner')
    useNavigateMock.mockReturnValue(vi.fn())
    useWhatsAppStatusMock.mockReturnValue({
      isPending: false,
      data: { state: 'connected', qrCodeDataUrl: null, detail: null },
    })
    useConnectWhatsAppMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
    useDiscoverAndSyncMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })

    render(<WhatsAppSetupPage />)

    expect(screen.getByRole('button', { name: /discover communities/i })).toBeEnabled()
  })
})
