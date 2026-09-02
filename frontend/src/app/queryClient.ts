import { QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'

/**
 * Global 401 handler for mid-session expiry: any query that fails with a
 * 401 (cookie expired/rejected after the initial `beforeLoad` check already
 * passed) hard-redirects to /login. A full navigation (rather than
 * router.navigate) sidesteps any circular import between the router and the
 * query client and guarantees all in-memory state is discarded along with
 * the now-invalid session.
 */
function handleQueryError(error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    if (window.location.pathname !== '/login') {
      window.location.assign('/login')
    }
  }
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: handleQueryError }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Any 4xx (not just 401) is a client error a retry can never fix —
      // the resource still won't exist, the request still won't be
      // authorized, the payload still won't validate. Retrying one anyway
      // just adds a few seconds of silent "still loading" before the
      // (already-determined) error state finally shows up.
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
        return failureCount < 2
      },
    },
  },
})
