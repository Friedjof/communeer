import { render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { GroupSummary } from '@/features/groups/types'
import { GroupSidebar } from './GroupSidebar'

const { useCommunityGroupsMock } = vi.hoisted(() => ({ useCommunityGroupsMock: vi.fn() }))

vi.mock('@/features/communities/queries', () => ({
  useCommunityGroups: useCommunityGroupsMock,
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to }: ComponentProps<'a'> & { to?: string }) => <a href={to}>{children}</a>,
}))

function group(overrides: Partial<GroupSummary> = {}): GroupSummary {
  return {
    id: 'group-1',
    waId: 'group-1@g.us',
    name: 'Marketplace',
    description: null,
    pictureUrl: null,
    isAnnouncementGroup: false,
    memberCount: 10,
    memberLimit: null,
    pendingRequestCount: 0,
    adminCount: 1,
    lastMessageAt: null,
    ...overrides,
  }
}

describe('GroupSidebar', () => {
  it('shows a skeleton while pending', () => {
    useCommunityGroupsMock.mockReturnValue({ isPending: true, isError: false, data: undefined })
    render(<GroupSidebar communityId="community-1" />)

    expect(screen.queryByText('Marketplace')).not.toBeInTheDocument()
    expect(screen.queryByText("Couldn't load groups.")).not.toBeInTheDocument()
  })

  it('shows a clear error state with a retry action when the groups query fails', () => {
    const refetch = vi.fn()
    useCommunityGroupsMock.mockReturnValue({ isPending: false, isError: true, data: undefined, refetch })
    render(<GroupSidebar communityId="community-1" />)

    // This used to silently fall through to "No groups found." — the same
    // message a genuinely empty community shows — with no way to recover.
    expect(screen.queryByText('No groups found.')).not.toBeInTheDocument()
    const retryButton = screen.getByRole('button', { name: 'Try again' })
    retryButton.click()
    expect(refetch).toHaveBeenCalledOnce()
  })

  it('renders the groups list on success', () => {
    useCommunityGroupsMock.mockReturnValue({
      isPending: false,
      isError: false,
      data: [group({ name: 'Marketplace' }), group({ id: 'group-2', name: 'Events' })],
    })
    render(<GroupSidebar communityId="community-1" />)

    expect(screen.getByText('Marketplace')).toBeInTheDocument()
    expect(screen.getByText('Events')).toBeInTheDocument()
  })
})
