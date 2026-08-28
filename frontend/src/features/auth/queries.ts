import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as authApi from './api'
import type { SessionUser } from './types'

export const authKeys = {
  session: ['auth', 'session'] as const,
}

export function sessionQueryOptions() {
  return queryOptions({
    queryKey: authKeys.session,
    queryFn: authApi.getSession,
    retry: false,
    staleTime: 5 * 60_000,
  })
}

export function useSession() {
  return useQuery(sessionQueryOptions())
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      authApi.login(credentials.username, credentials.password),
    onSuccess: (user: SessionUser) => {
      queryClient.setQueryData(authKeys.session, user)
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: authApi.logout,
    onSuccess: () => {
      queryClient.setQueryData(authKeys.session, null)
      queryClient.clear()
    },
  })
}
