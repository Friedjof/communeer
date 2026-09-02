import { apiGet, apiPatch, apiPost } from '@/api/client'
import type { CreateUserInput, ManagedUser, UpdateUserInput } from './types'

export function listUsers(): Promise<ManagedUser[]> {
  return apiGet<ManagedUser[]>('/users')
}

export function createUser(input: CreateUserInput): Promise<ManagedUser> {
  return apiPost<ManagedUser>('/users', input)
}

export function updateUser(userId: string, input: UpdateUserInput): Promise<ManagedUser> {
  return apiPatch<ManagedUser>(`/users/${userId}`, input)
}

export function resetUserPassword(userId: string, password: string): Promise<void> {
  return apiPost<void>(`/users/${userId}/reset-password`, { password })
}

export function resetUserTotp(userId: string): Promise<void> {
  return apiPost<void>(`/users/${userId}/reset-2fa`)
}

export function resendClaimCode(userId: string): Promise<void> {
  return apiPost<void>(`/users/${userId}/resend-claim`)
}

export function approveGroupAdmin(userId: string): Promise<void> {
  return apiPost<void>(`/users/${userId}/approve`)
}
