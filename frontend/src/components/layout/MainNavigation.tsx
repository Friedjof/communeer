import { Link } from '@tanstack/react-router'
import { LayoutDashboard, ScrollText, Settings, ShieldAlert, Users } from 'lucide-react'
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
  // Moderation and the audit log are owner/admin-only on the backend (see
  // `moderation/router.py`/`audit/router.py`) — `group_admin` gets a 403
  // just like `viewer`, so both are hidden here.
  const hidesModerationAndAudit = session.data?.role === 'viewer' || session.data?.role === 'group_admin'

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
          {hidesModerationAndAudit ? null : (
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
      {hidesModerationAndAudit ? null : (
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
