export type UserRole = 'owner' | 'admin' | 'viewer'

export interface SessionUser {
  id: string
  username: string
  role: UserRole
}
