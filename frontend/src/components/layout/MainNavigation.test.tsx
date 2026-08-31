import { render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { SessionUser } from '@/features/auth/types'
import { MainNavigation } from './MainNavigation'

const { useSessionMock } = vi.hoisted(() => ({ useSessionMock: vi.fn() }))

vi.mock('@/features/auth/queries', () => ({
  useSession: useSessionMock,
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to, onClick }: ComponentProps<'a'> & { to?: string }) => (
    <a href={to} onClick={onClick as never}>
      {children}
    </a>
  ),
}))

function mockSession(role: SessionUser['role'] | undefined) {
  useSessionMock.mockReturnValue({
    data: role ? { id: '1', username: 'user', role } : undefined,
  })
}

describe('MainNavigation', () => {
  it('hides Moderation and Audit log links for a viewer', () => {
    mockSession('viewer')
    render(<MainNavigation communityId="community-1" />)

    expect(screen.queryByText('Moderation')).not.toBeInTheDocument()
    expect(screen.queryByText('Audit log')).not.toBeInTheDocument()
    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Members')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('shows Moderation and Audit log links for an owner', () => {
    mockSession('owner')
    render(<MainNavigation communityId="community-1" />)

    expect(screen.getByText('Moderation')).toBeInTheDocument()
    expect(screen.getByText('Audit log')).toBeInTheDocument()
  })
})
