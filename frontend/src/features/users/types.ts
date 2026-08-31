import type { UserRole } from '@/features/auth/types'

export interface ManagedUser {
  id: string
  username: string
  role: UserRole
  isActive: boolean
  createdAt: string
}

export interface CreateUserInput {
  username: string
  password: string
  role: UserRole
}

export interface UpdateUserInput {
  role?: UserRole
  isActive?: boolean
}
