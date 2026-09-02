import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as authApi from './api'
import type { CompleteClaimInput, SessionUser } from './types'

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
    onSuccess: (result) => {
      if (!result.requiresTotp) {
        queryClient.setQueryData(authKeys.session, result.user)
      }
    },
  })
}

export function useVerifyLoginTotp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => authApi.verifyLoginTotp(code),
    onSuccess: (user: SessionUser) => {
      queryClient.setQueryData(authKeys.session, user)
    },
  })
}

export function useRequestLoginWhatsappOtp() {
  return useMutation({
    mutationFn: authApi.requestLoginWhatsappOtp,
  })
}

export function useVerifyLoginWhatsappOtp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => authApi.verifyLoginWhatsappOtp(code),
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

export function useSetupTotp() {
  return useMutation({
    mutationFn: authApi.setupTotp,
  })
}

export function useEnableTotp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => authApi.enableTotp(code),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: authKeys.session })
    },
  })
}

export function useDisableTotp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (password: string) => authApi.disableTotp(password),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: authKeys.session })
    },
  })
}

export function useRegenerateRecoveryCodes() {
  return useMutation({
    mutationFn: (password: string) => authApi.regenerateRecoveryCodes(password),
  })
}

export function useSetupWhatsAppOtp() {
  return useMutation({
    mutationFn: (phoneNumber: string) => authApi.setupWhatsAppOtp(phoneNumber),
  })
}

export function useEnableWhatsAppOtp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => authApi.enableWhatsAppOtp(code),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: authKeys.session })
    },
  })
}

export function useDisableWhatsAppOtp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (password: string) => authApi.disableWhatsAppOtp(password),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: authKeys.session })
    },
  })
}

export function useRequestClaim() {
  return useMutation({
    mutationFn: (phoneNumber: string) => authApi.requestClaim(phoneNumber),
  })
}

export function useCompleteClaim() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CompleteClaimInput) => authApi.completeClaim(input),
    onSuccess: (user) => {
      queryClient.setQueryData(authKeys.session, user)
    },
  })
}
