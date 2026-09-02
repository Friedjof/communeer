import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { SessionUser } from '@/features/auth/types'
import { StartRenewalSection } from './StartRenewalSection'
import type { RenewalSuggestion } from '../types'

const { useSessionMock, useRenewalSuggestionsMock } = vi.hoisted(() => ({
  useSessionMock: vi.fn(),
  useRenewalSuggestionsMock: vi.fn(),
}))

vi.mock('@/features/auth/queries', () => ({
  useSession: useSessionMock,
}))

vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>()
  return {
    ...actual,
    useRenewalSuggestions: useRenewalSuggestionsMock,
  }
})

const suggestion: RenewalSuggestion = {
  memberId: 'member-1',
  waId: '491234567890',
  displayName: 'Alice',
  avatarUrl: null,
  phoneNumberMasked: '+49 *** ** 90',
  joinedAt: '2025-01-01T00:00:00Z',
  lastMessageAt: null,
  lastSeenAt: null,
}

function mockSession(role: SessionUser['role']) {
  useSessionMock.mockReturnValue({ data: { id: '1', username: 'user', role } })
}

function renderSection(role: SessionUser['role']) {
  mockSession(role)
  useRenewalSuggestionsMock.mockReturnValue({
    isPending: false,
    isError: false,
    data: [suggestion],
    refetch: vi.fn(),
  })
  const queryClient = new QueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <StartRenewalSection groupId="group-1" groupName="Test Group" onCampaignCreated={vi.fn()} />
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

describe('StartRenewalSection', () => {
  it('disables the Start renewal button for a viewer', () => {
    renderSection('viewer')
    expect(screen.getByRole('button', { name: /start renewal for/i })).toBeDisabled()
  })

  it('enables the Start renewal button for an owner once a member is selected', async () => {
    renderSection('owner')
    await userEvent.click(screen.getByRole('button', { name: /select all/i }))
    expect(screen.getByRole('button', { name: /start renewal for 1 member/i })).toBeEnabled()
  })
})
