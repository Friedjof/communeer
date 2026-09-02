import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as usersApi from './api'
import type { CreateUserInput, UpdateUserInput } from './types'

export const usersKeys = {
  all: ['users'] as const,
}

export function useUsers() {
  return useQuery({
    queryKey: usersKeys.all,
    queryFn: usersApi.listUsers,
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateUserInput) => usersApi.createUser(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: usersKeys.all })
    },
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, input }: { userId: string; input: UpdateUserInput }) => usersApi.updateUser(userId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: usersKeys.all })
    },
  })
}

export function useResetUserPassword() {
  return useMutation({
    mutationFn: ({ userId, password }: { userId: string; password: string }) =>
      usersApi.resetUserPassword(userId, password),
  })
}

export function useResetUserTotp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => usersApi.resetUserTotp(userId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: usersKeys.all })
    },
  })
}

export function useResendClaimCode() {
  return useMutation({
    mutationFn: (userId: string) => usersApi.resendClaimCode(userId),
  })
}

export function useApproveGroupAdmin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => usersApi.approveGroupAdmin(userId),
    // `onSettled`, not `onSuccess`: the backend sets `isApproved` *before*
    // attempting the send (see `approve_group_admin`), so even a failed
    // call (a 503 if the WhatsApp send itself fails) still needs the row
    // to re-render out of "Pending approval" — the approval already stuck,
    // only the message needs a retry via "Resend claim code".
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: usersKeys.all })
    },
  })
}
