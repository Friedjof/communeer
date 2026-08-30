import { Link } from '@tanstack/react-router'
import { LayoutDashboard, ScrollText, Settings, ShieldAlert, UserCheck, Users } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/lib/uiStore'
import { useSession } from '@/features/auth/queries'

interface MainNavigationProps {
  communityId?: string
  className?: string
  onNavigate?: () => void
}

export function MainNavigation({ communityId, className, onNavigate }: MainNavigationProps) {
  const persistedCommunityId = useUiStore((state) => state.selectedCommunityId)
  const activeCommunityId = communityId ?? persistedCommunityId ?? undefined
  const session = useSession()
  const isViewer = session.data?.role === 'viewer'

  const linkClass =
    'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground data-[status=active]:bg-primary/10 data-[status=active]:text-primary'

  return (
    <nav className={cn('flex items-center gap-1', className)}>
      {activeCommunityId ? (
        <>
          <Link
            to="/c/$communityId"
            params={{ communityId: activeCommunityId }}
            activeOptions={{ exact: true }}
            className={linkClass}
            onClick={onNavigate}
          >
            <LayoutDashboard className="size-4" />
            Overview
          </Link>
          <Link
            to="/c/$communityId/members"
            params={{ communityId: activeCommunityId }}
            className={linkClass}
            onClick={onNavigate}
          >
            <Users className="size-4" />
            Members
          </Link>
          <Link
            to="/c/$communityId/renewals"
            params={{ communityId: activeCommunityId }}
            className={linkClass}
            onClick={onNavigate}
          >
            <UserCheck className="size-4" />
            Renewals
          </Link>
          {isViewer ? null : (
            <Link
              to="/c/$communityId/moderation"
              params={{ communityId: activeCommunityId }}
              className={linkClass}
              onClick={onNavigate}
            >
              <ShieldAlert className="size-4" />
              Moderation
            </Link>
          )}
        </>
      ) : null}
      {isViewer ? null : (
        <Link to="/audit" className={linkClass} onClick={onNavigate}>
          <ScrollText className="size-4" />
          Audit log
        </Link>
      )}
      <Link to="/settings" className={linkClass} onClick={onNavigate}>
        <Settings className="size-4" />
        Settings
      </Link>
    </nav>
  )
}
