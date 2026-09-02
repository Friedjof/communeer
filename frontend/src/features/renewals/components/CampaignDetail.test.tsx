import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { SessionUser } from '@/features/auth/types'
import { CampaignDetail } from './CampaignDetail'
import type { RenewalCampaignDetail } from '../types'

const {
  useSessionMock,
  useRenewalCampaignMock,
  useConfirmRenewalMock,
  useSendRenewalReminderMock,
  useRemoveFromCampaignMock,
  useCheckRenewalReactionsMock,
  useProcessDueRemovalsMock,
  useNonRespondersMock,
} = vi.hoisted(() => ({
  useSessionMock: vi.fn(),
  useRenewalCampaignMock: vi.fn(),
  useConfirmRenewalMock: vi.fn(),
  useSendRenewalReminderMock: vi.fn(),
  useRemoveFromCampaignMock: vi.fn(),
  useCheckRenewalReactionsMock: vi.fn(),
  useProcessDueRemovalsMock: vi.fn(),
  useNonRespondersMock: vi.fn(),
}))

vi.mock('@/features/auth/queries', () => ({
  useSession: useSessionMock,
}))

vi.mock('../queries', () => ({
  useRenewalCampaign: useRenewalCampaignMock,
  useConfirmRenewal: useConfirmRenewalMock,
  useSendRenewalReminder: useSendRenewalReminderMock,
  useRemoveFromCampaign: useRemoveFromCampaignMock,
  useCheckRenewalReactions: useCheckRenewalReactionsMock,
  useProcessDueRemovals: useProcessDueRemovalsMock,
  useNonResponders: useNonRespondersMock,
}))

const campaign: RenewalCampaignDetail = {
  id: 'campaign-1',
  groupId: 'group-1',
  startedAt: '2026-01-01T00:00:00Z',
  deadline: '2026-01-08T00:00:00Z',
  pendingCount: 1,
  confirmedCount: 0,
  expiredCount: 0,
  totalCount: 1,
  archivedAt: null,
  confirmations: [
    {
      memberId: 'member-1',
      waId: '491234567890',
      displayName: 'Alice',
      status: 'pending',
      isExpired: false,
      respondedAt: null,
      reminderSentAt: null,
      declinedAt: null,
      removedAt: null,
    },
  ],
}

function mockSession(role: SessionUser['role']) {
  useSessionMock.mockReturnValue({ data: { id: '1', username: 'user', role } })
}

function setup(role: SessionUser['role']) {
  mockSession(role)
  useRenewalCampaignMock.mockReturnValue({ isPending: false, isError: false, data: campaign })
  useConfirmRenewalMock.mockReturnValue({ mutate: vi.fn(), isPending: false, variables: undefined })
  useSendRenewalReminderMock.mockReturnValue({ mutate: vi.fn(), isPending: false, variables: undefined })
  useRemoveFromCampaignMock.mockReturnValue({ mutate: vi.fn(), isPending: false, variables: undefined })
  useCheckRenewalReactionsMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
  useProcessDueRemovalsMock.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null })
  useNonRespondersMock.mockReturnValue({ isPending: false, isError: false, data: [] })
}

describe('CampaignDetail', () => {
  it('disables Mark confirmed for a viewer', () => {
    setup('viewer')
    render(
      <TooltipProvider>
        <CampaignDetail campaignId="campaign-1" groupName="Test Group" />
      </TooltipProvider>,
    )

    expect(screen.getByRole('button', { name: 'Mark confirmed' })).toBeDisabled()
  })

  it('enables Mark confirmed for an owner', () => {
    setup('owner')
    render(
      <TooltipProvider>
        <CampaignDetail campaignId="campaign-1" groupName="Test Group" />
      </TooltipProvider>,
    )

    expect(screen.getByRole('button', { name: 'Mark confirmed' })).toBeEnabled()
  })

  it('shows the exact reminder text before sending, and only sends after confirming', async () => {
    setup('owner')
    const mutate = vi.fn()
    useSendRenewalReminderMock.mockReturnValue({ mutate, isPending: false, variables: undefined })
    render(
      <TooltipProvider>
        <CampaignDetail campaignId="campaign-1" groupName="Maple Street Neighbors" />
      </TooltipProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Send reminder' }))
    expect(mutate).not.toHaveBeenCalled()
    expect(screen.getByText(/Maple Street Neighbors/)).toBeInTheDocument()
    expect(screen.getByText(/We're checking in on who'd like to stay part of/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(mutate).toHaveBeenCalledWith('member-1', expect.anything())
  })
})
