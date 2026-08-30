import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { SessionUser } from '@/features/auth/types'
import { CommunityOverviewPage } from './CommunityOverviewPage'
import type { CommunityDetail } from './types'

const {
  useSessionMock,
  useCommunityMock,
  useCommunityGroupsMock,
  useCommunityGroupsHistoryMock,
  useSyncCommunityMock,
  useCommunityMembersMock,
} = vi.hoisted(() => ({
  useSessionMock: vi.fn(),
  useCommunityMock: vi.fn(),
  useCommunityGroupsMock: vi.fn(),
  useCommunityGroupsHistoryMock: vi.fn(),
  useSyncCommunityMock: vi.fn(),
  useCommunityMembersMock: vi.fn(),
}))

vi.mock('@/features/auth/queries', () => ({
  useSession: useSessionMock,
}))

vi.mock('./queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./queries')>()
  return {
    ...actual,
    useCommunity: useCommunityMock,
    useCommunityGroups: useCommunityGroupsMock,
    useCommunityGroupsHistory: useCommunityGroupsHistoryMock,
    useSyncCommunity: useSyncCommunityMock,
  }
})

vi.mock('../members/queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../members/queries')>()
  return {
    ...actual,
    useCommunityMembers: useCommunityMembersMock,
  }
})

// These are chart/list widgets unrelated to the role-gating this test
// covers; stub them out so the test doesn't depend on their internals
// (they have their own data-fetching hooks) and isn't coupled to a part of
// the tree owned by a different workstream.
vi.mock('./components/AdminsList', () => ({ AdminsList: () => null }))
vi.mock('./components/CommunityGrowthChart', () => ({ CommunityGrowthChart: () => null }))
vi.mock('./components/GroupGrowthChart', () => ({ GroupGrowthChart: () => null }))
vi.mock('./components/NeedsAttentionList', () => ({ NeedsAttentionList: () => null }))
vi.mock('./components/RecentlyJoinedList', () => ({ RecentlyJoinedList: () => null }))

const community: CommunityDetail = {
  id: 'community-1',
  waId: 'wa-1',
  name: 'Test Community',
  pictureUrl: null,
  memberCount: 10,
  groupCount: 2,
  adminCount: 1,
  pendingRequestCount: 0,
  lastSyncedAt: '2026-01-01T00:00:00Z',
  description: null,
  announcementGroupWaId: 'wa-announce',
}

function mockSession(role: SessionUser['role']) {
  useSessionMock.mockReturnValue({ data: { id: '1', username: 'user', role } })
}

function renderPage(role: SessionUser['role']) {
  mockSession(role)
  useCommunityMock.mockReturnValue({ isPending: false, isError: false, data: community, refetch: vi.fn() })
  useCommunityGroupsMock.mockReturnValue({ isPending: false, isError: false, data: [], refetch: vi.fn() })
  useCommunityGroupsHistoryMock.mockReturnValue({ data: undefined })
  useCommunityMembersMock.mockReturnValue({ isPending: false, isError: false, data: [], refetch: vi.fn() })
  useSyncCommunityMock.mockReturnValue({ mutate: vi.fn(), isPending: false })

  render(
    <TooltipProvider>
      <CommunityOverviewPage communityId="community-1" />
    </TooltipProvider>,
  )
}

describe('CommunityOverviewPage', () => {
  it('disables the Sync now button for a viewer', () => {
    renderPage('viewer')
    expect(screen.getByRole('button', { name: /sync now/i })).toBeDisabled()
  })

  it('enables the Sync now button for an owner', () => {
    renderPage('owner')
    expect(screen.getByRole('button', { name: /sync now/i })).toBeEnabled()
  })
})
