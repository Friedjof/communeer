import type { QueryClient } from '@tanstack/react-query'
import {
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
  useNavigate,
  useParams,
} from '@tanstack/react-router'
import { ApiError } from '@/api/client'
import { AppShell } from '@/components/layout/AppShell'
import { CommunityShell } from '@/components/layout/CommunityShell'
import { EmptyState } from '@/components/feedback/EmptyState'
import { sessionQueryOptions } from '@/features/auth/queries'
import { LoginPage } from '@/features/auth/LoginPage'
import { CommunityOverviewPage } from '@/features/communities/CommunityOverviewPage'
import { communitiesQueryOptions } from '@/features/communities/queries'
import { GroupDetailPage } from '@/features/groups/GroupDetailPage'
import type { GroupDetailTab } from '@/features/groups/types'
import { CommunityMembersPage } from '@/features/members/CommunityMembersPage'
import { RenewalsPage } from '@/features/renewals/RenewalsPage'
import { AuditLogPage } from '@/features/audit/AuditLogPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { WhatsAppSetupPage } from '@/features/whatsapp/WhatsAppSetupPage'
import { whatsappStatusQueryOptions } from '@/features/whatsapp/queries'
import { useUiStore } from '@/lib/uiStore'
import { queryClient } from './queryClient'

interface RouterContext {
  queryClient: QueryClient
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  component: LoginPage,
})

/**
 * Pathless authenticated layout: every descendant route requires a valid
 * session. `beforeLoad` fetches `GET /api/v1/session` through the query
 * cache; a 401 `ApiError` redirects to /login. This only guards the
 * initial navigation/reload — a 401 that happens later (mid-session cookie
 * expiry on an already-mounted page) is caught by the global QueryCache
 * handler in app/queryClient.ts instead.
 */
const authenticatedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: '_authenticated',
  beforeLoad: async ({ context, location }) => {
    try {
      await context.queryClient.ensureQueryData(sessionQueryOptions())
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        throw redirect({ to: '/login' })
      }
      throw error
    }

    const whatsapp = await context.queryClient.ensureQueryData(whatsappStatusQueryOptions())
    if (whatsapp.state !== 'connected' && location.pathname !== '/setup/whatsapp') {
      throw redirect({ to: '/setup/whatsapp' })
    }
  },
  component: AuthenticatedLayout,
})

function AuthenticatedLayout() {
  const { communityId } = useParams({ strict: false })
  const persistedCommunityId = useUiStore((state) => state.selectedCommunityId)
  return (
    <AppShell communityId={communityId ?? persistedCommunityId ?? undefined}>
      <Outlet />
    </AppShell>
  )
}

const indexRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/',
  beforeLoad: async ({ context }) => {
    const communities = await context.queryClient.ensureQueryData(communitiesQueryOptions())
    if (communities.length === 0) return
    const persistedId = useUiStore.getState().selectedCommunityId
    const target = communities.find((community) => community.id === persistedId)?.id ?? communities[0]?.id
    if (target) {
      throw redirect({ to: '/c/$communityId', params: { communityId: target } })
    }
  },
  component: () => (
    <div className="p-6">
      <EmptyState title="No communities yet" description="Once a WhatsApp community is synced, it will show up here." />
    </div>
  ),
})

const communityLayoutRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: 'c/$communityId',
  beforeLoad: ({ params }) => {
    useUiStore.getState().setSelectedCommunityId(params.communityId)
  },
  component: CommunityLayoutComponent,
})

function CommunityLayoutComponent() {
  const { communityId } = communityLayoutRoute.useParams()
  const { groupId } = useParams({ strict: false })
  return (
    <CommunityShell communityId={communityId} currentGroupId={groupId}>
      <Outlet />
    </CommunityShell>
  )
}

const communityIndexRoute = createRoute({
  getParentRoute: () => communityLayoutRoute,
  path: '/',
  component: () => {
    const { communityId } = communityLayoutRoute.useParams()
    return <CommunityOverviewPage communityId={communityId} />
  },
})

const communityMembersRoute = createRoute({
  getParentRoute: () => communityLayoutRoute,
  path: 'members',
  component: () => {
    const { communityId } = communityLayoutRoute.useParams()
    return <CommunityMembersPage communityId={communityId} />
  },
})

interface RenewalsSearch {
  campaignId?: string
}

const communityRenewalsRoute = createRoute({
  getParentRoute: () => communityLayoutRoute,
  path: 'renewals',
  validateSearch: (search: Record<string, unknown>): RenewalsSearch => ({
    campaignId: typeof search.campaignId === 'string' ? search.campaignId : undefined,
  }),
  component: RenewalsRouteComponent,
})

function RenewalsRouteComponent() {
  const { communityId } = communityLayoutRoute.useParams()
  const { campaignId } = communityRenewalsRoute.useSearch()
  const navigate = useNavigate()

  return (
    <RenewalsPage
      communityId={communityId}
      selectedCampaignId={campaignId ?? null}
      onSelectCampaign={(nextCampaignId) =>
        void navigate({
          to: '/c/$communityId/renewals',
          params: { communityId },
          search: { campaignId: nextCampaignId ?? undefined },
          replace: true,
        })
      }
    />
  )
}

interface GroupDetailSearch {
  tab: GroupDetailTab
}

const VALID_TABS: GroupDetailTab[] = ['overview', 'members', 'requests', 'advanced']

const groupDetailRoute = createRoute({
  getParentRoute: () => communityLayoutRoute,
  path: 'groups/$groupId',
  validateSearch: (search: Record<string, unknown>): GroupDetailSearch => ({
    tab: VALID_TABS.includes(search.tab as GroupDetailTab) ? (search.tab as GroupDetailTab) : 'overview',
  }),
  component: GroupDetailRouteComponent,
})

function GroupDetailRouteComponent() {
  const { communityId, groupId } = groupDetailRoute.useParams()
  const { tab } = groupDetailRoute.useSearch()
  const navigate = useNavigate()

  return (
    <GroupDetailPage
      groupId={groupId}
      tab={tab}
      onTabChange={(nextTab) =>
        void navigate({
          to: '/c/$communityId/groups/$groupId',
          params: { communityId, groupId },
          search: { tab: nextTab },
          replace: true,
        })
      }
    />
  )
}

/** Deep-link straight into the Members tab of a group. */
const groupMembersDeepLinkRoute = createRoute({
  getParentRoute: () => communityLayoutRoute,
  path: 'groups/$groupId/members',
  beforeLoad: ({ params }) => {
    throw redirect({
      to: '/c/$communityId/groups/$groupId',
      params: { communityId: params.communityId, groupId: params.groupId },
      search: { tab: 'members' },
      replace: true,
    })
  },
})

const auditRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/audit',
  component: () => (
    <div className="p-4 md:p-6">
      <AuditLogPage />
    </div>
  ),
})

const settingsRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/settings',
  component: () => (
    <div className="p-4 md:p-6">
      <SettingsPage />
    </div>
  ),
})

const whatsappSetupRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/setup/whatsapp',
  component: WhatsAppSetupPage,
})

const communityRouteTree = communityLayoutRoute.addChildren([
  communityIndexRoute,
  communityMembersRoute,
  communityRenewalsRoute,
  groupDetailRoute,
  groupMembersDeepLinkRoute,
])

const authenticatedRouteTree = authenticatedRoute.addChildren([
  indexRoute,
  communityRouteTree,
  auditRoute,
  settingsRoute,
  whatsappSetupRoute,
])

const routeTree = rootRoute.addChildren([loginRoute, authenticatedRouteTree])

export const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: 'intent',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
