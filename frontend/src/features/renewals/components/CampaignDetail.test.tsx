import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { SessionUser } from '@/features/auth/types'
import { CampaignDetail } from './CampaignDetail'
import type { RenewalCampaignDetail } from '../types'

const { useSessionMock, useRenewalCampaignMock, useConfirmRenewalMock, useNonRespondersMock } = vi.hoisted(() => ({
  useSessionMock: vi.fn(),
  useRenewalCampaignMock: vi.fn(),
  useConfirmRenewalMock: vi.fn(),
  useNonRespondersMock: vi.fn(),
}))

vi.mock('@/features/auth/queries', () => ({
  useSession: useSessionMock,
}))

vi.mock('../queries', () => ({
  useRenewalCampaign: useRenewalCampaignMock,
  useConfirmRenewal: useConfirmRenewalMock,
  useNonResponders: useNonRespondersMock,
}))

const campaign: RenewalCampaignDetail = {
  id: 'campaign-1',
  communityId: 'community-1',
  startedAt: '2026-01-01T00:00:00Z',
  deadline: '2026-01-08T00:00:00Z',
  pendingCount: 1,
  confirmedCount: 0,
  expiredCount: 0,
  totalCount: 1,
  confirmations: [
    {
      memberId: 'member-1',
      waId: '491234567890',
      displayName: 'Alice',
      status: 'pending',
      isExpired: false,
      respondedAt: null,
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
  useNonRespondersMock.mockReturnValue({ isPending: false, isError: false, data: [] })
}

describe('CampaignDetail', () => {
  it('disables Mark confirmed for a viewer', () => {
    setup('viewer')
    render(
      <TooltipProvider>
        <CampaignDetail campaignId="campaign-1" />
      </TooltipProvider>,
    )

    expect(screen.getByRole('button', { name: 'Mark confirmed' })).toBeDisabled()
  })

  it('enables Mark confirmed for an owner', () => {
    setup('owner')
    render(
      <TooltipProvider>
        <CampaignDetail campaignId="campaign-1" />
      </TooltipProvider>,
    )

    expect(screen.getByRole('button', { name: 'Mark confirmed' })).toBeEnabled()
  })
})
