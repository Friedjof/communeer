// oxlint-disable react/only-export-components -- this file's job is the
// router config (`export const router`), not component authoring; each
// route's tiny layout component is deliberately kept inline next to its
// `createRoute` call for readability, so Fast Refresh doesn't apply here.
import type { QueryClient } from '@tanstack/react-query'
import {
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  lazyRouteComponent,
  redirect,
  useNavigate,
  useParams,
  useRouterState,
} from '@tanstack/react-router'
import { ApiError } from '@/api/client'
import { AppShell } from '@/components/layout/AppShell'
import { CommunityShell } from '@/components/layout/CommunityShell'
import { EmptyState } from '@/components/feedback/EmptyState'
import { RoutePendingFallback } from '@/components/feedback/LoadingSkeletons'
import { sessionQueryOptions } from '@/features/auth/queries'
import { LoginPage } from '@/features/auth/LoginPage'
import { communitiesQueryOptions } from '@/features/communities/queries'
import type { GroupDetailTab } from '@/features/groups/types'
import { WhatsAppSetupPage } from '@/features/whatsapp/WhatsAppSetupPage'
import { whatsappStatusQueryOptions } from '@/features/whatsapp/queries'
import { useUiStore } from '@/lib/uiStore'
import { queryClient } from './queryClient'

// Code-split the heavier feature pages: route matching / `beforeLoad` (the
// auth guard above) stays eager, only the page `component` itself is
// deferred to its own chunk. `lazyRouteComponent` throws the in-flight
// import promise, which each route's own `pendingComponent`-driven Suspense
// boundary (see `Match`/`MatchView` in tanstack/react-router) catches —
// so a route transition shows `RoutePendingFallback` instead of a blank gap
// while the chunk downloads. `LoginPage`/`WhatsAppSetupPage` and the
// shell/auth-guard routes stay eagerly imported above — they're needed
// immediately (or are small) and don't need splitting.
const CommunityOverviewPage = lazyRouteComponent(
  () => import('@/features/communities/CommunityOverviewPage'),
  'CommunityOverviewPage',
)
const GroupDetailPage = lazyRouteComponent(() => import('@/features/groups/GroupDetailPage'), 'GroupDetailPage')
const CommunityMembersPage = lazyRouteComponent(
  () => import('@/features/members/CommunityMembersPage'),
  'CommunityMembersPage',
)
const ModerationPage = lazyRouteComponent(() => import('@/features/moderation/ModerationPage'), 'ModerationPage')
const SettingsPage = lazyRouteComponent(() => import('@/features/settings/SettingsPage'), 'SettingsPage')
const RenewalsPage = lazyRouteComponent(() => import('@/features/renewals/RenewalsPage'), 'RenewalsPage')
const AuditLogPage = lazyRouteComponent(() => import('@/features/audit/AuditLogPage'), 'AuditLogPage')

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

/** Coarse top-level section key (`/c`, `/audit`, `/settings`, `/setup`, …) —
 * deliberately not the full pathname, so switching communities or tabs
 * within `/c/*` doesn't force-remount `AppShell`'s children; it only fades
 * in when moving between fundamentally different sections of the app. */
function topLevelSectionKey(pathname: string): string {
  return pathname.split('/')[1] ?? ''
}

function AuthenticatedLayout() {
  const { communityId } = useParams({ strict: false })
  const persistedCommunityId = useUiStore((state) => state.selectedCommunityId)
  const sectionKey = useRouterState({ select: (state) => topLevelSectionKey(state.location.pathname) })
  return (
    <AppShell communityId={communityId ?? persistedCommunityId ?? undefined}>
      <div key={sectionKey} className="animate-in fade-in duration-200">
        <Outlet />
      </div>
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
  // Full pathname (community + sub-page + group id) so switching communities,
  // switching between overview/members/renewals/moderation, or opening a
  // different group all get a subtle fade rather than an instant swap —
  // while `CommunityShell` itself (the sidebar/nav chrome) stays mounted.
  const routeKey = useRouterState({ select: (state) => state.location.pathname })
  return (
    <CommunityShell communityId={communityId} currentGroupId={groupId}>
      <div key={routeKey} className="animate-in fade-in duration-200">
        <Outlet />
      </div>
    </CommunityShell>
  )
}

const communityIndexRoute = createRoute({
  getParentRoute: () => communityLayoutRoute,
  path: '/',
  pendingComponent: RoutePendingFallback,
  component: () => {
    const { communityId } = communityLayoutRoute.useParams()
    return <CommunityOverviewPage communityId={communityId} />
  },
})

const communityMembersRoute = createRoute({
  getParentRoute: () => communityLayoutRoute,
  path: 'members',
  pendingComponent: RoutePendingFallback,
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
  pendingComponent: RoutePendingFallback,
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
  pendingComponent: RoutePendingFallback,
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

const communityModerationRoute = createRoute({
  getParentRoute: () => communityLayoutRoute,
  path: 'moderation',
  pendingComponent: RoutePendingFallback,
  component: () => {
    const { communityId } = communityLayoutRoute.useParams()
    return <ModerationPage communityId={communityId} />
  },
})

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
  pendingComponent: RoutePendingFallback,
  component: () => (
    <div className="p-4 md:p-6">
      <AuditLogPage />
    </div>
  ),
})

const settingsRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/settings',
  pendingComponent: RoutePendingFallback,
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
  communityModerationRoute,
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
