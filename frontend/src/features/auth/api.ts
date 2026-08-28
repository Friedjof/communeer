import { apiGet, apiPost } from '@/api/client'
import type { SessionUser } from './types'

export function login(username: string, password: string): Promise<SessionUser> {
  return apiPost<SessionUser>('/auth/login', { username, password })
}

export function logout(): Promise<void> {
  return apiPost<void>('/auth/logout')
}

export function getSession(): Promise<SessionUser> {
  return apiGet<SessionUser>('/session')
}
