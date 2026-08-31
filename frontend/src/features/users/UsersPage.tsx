import { useState } from 'react'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ListSkeleton } from '@/components/feedback/LoadingSkeletons'
import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useSession } from '@/features/auth/queries'
import type { UserRole } from '@/features/auth/types'
import { cn } from '@/lib/utils'
import { formatDate } from '@/lib/format'
import { useCreateUser, useResetUserPassword, useUpdateUser, useUsers } from './queries'
import type { ManagedUser } from './types'

const ROLE_OPTIONS: UserRole[] = ['owner', 'admin', 'viewer']

const ROLE_DESCRIPTIONS: Record<UserRole, string> = {
  owner: 'Full access, including managing the team.',
  admin: 'Manage groups, members, and moderation.',
  viewer: 'Read-only access.',
}

function ApiErrorText({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
  return <p className="text-sm text-destructive">{message}</p>
}

function RoleCard({
  role,
  selected,
  onSelect,
}: {
  role: UserRole
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'flex flex-col gap-1 rounded-lg border p-3 text-left text-sm transition-colors hover:bg-muted/60',
        selected ? 'border-primary bg-primary/5' : 'border-input',
      )}
    >
      <span className="font-medium capitalize">{role}</span>
      <span className="text-xs text-muted-foreground">{ROLE_DESCRIPTIONS[role]}</span>
    </button>
  )
}

function CreateUserDialog() {
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('admin')
  const createUser = useCreateUser()

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setUsername('')
          setPassword('')
          setRole('admin')
          createUser.reset()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button>New user</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create a new user</DialogTitle>
          <DialogDescription>They can log in with this username and password right away.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="new-user-username" className="text-sm font-medium">
                Username
              </label>
              <Input id="new-user-username" value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="new-user-password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="new-user-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <span className="text-xs text-muted-foreground">Minimum 8 characters</span>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Role</span>
            <div className="grid grid-cols-3 gap-3">
              {ROLE_OPTIONS.map((option) => (
                <RoleCard key={option} role={option} selected={role === option} onSelect={() => setRole(option)} />
              ))}
            </div>
          </div>

          <ApiErrorText error={createUser.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            disabled={createUser.isPending || username.length === 0 || password.length < 8}
            onClick={() => {
              createUser.mutate(
                { username, password, role },
                { onSuccess: () => setOpen(false) },
              )
            }}
          >
            {createUser.isPending ? 'Creating…' : 'Create user'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ResetPasswordDialog({ user }: { user: ManagedUser }) {
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const resetPassword = useResetUserPassword()

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setPassword('')
          resetPassword.reset()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Reset password
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Reset password for {user.username}</DialogTitle>
          <DialogDescription>They'll need to use this new password on their next login.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="reset-password-input" className="text-sm font-medium">
            New password
          </label>
          <Input
            id="reset-password-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className="text-xs text-muted-foreground">Minimum 8 characters</span>
          <ApiErrorText error={resetPassword.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            disabled={resetPassword.isPending || password.length < 8}
            onClick={() => {
              resetPassword.mutate({ userId: user.id, password }, { onSuccess: () => setOpen(false) })
            }}
          >
            {resetPassword.isPending ? 'Resetting…' : 'Reset password'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function UserRow({ user, currentUserId }: { user: ManagedUser; currentUserId?: string }) {
  const updateUser = useUpdateUser()
  const isSelf = user.id === currentUserId

  return (
    <TableRow>
      <TableCell className="font-medium">
        {user.username}
        {isSelf ? (
          <Badge variant="secondary" className="ml-2">
            You
          </Badge>
        ) : null}
      </TableCell>
      <TableCell>
        <Select
          value={user.role}
          onValueChange={(value) => updateUser.mutate({ userId: user.id, input: { role: value as UserRole } })}
        >
          <SelectTrigger size="sm" className="capitalize">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ROLE_OPTIONS.map((option) => (
              <SelectItem key={option} value={option} className="capitalize">
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell>
        <Checkbox
          checked={user.isActive}
          disabled={isSelf}
          onCheckedChange={(checked) =>
            updateUser.mutate({ userId: user.id, input: { isActive: checked === true } })
          }
        />
      </TableCell>
      <TableCell className="text-muted-foreground">{formatDate(user.createdAt)}</TableCell>
      <TableCell className="text-right">
        <ResetPasswordDialog user={user} />
      </TableCell>
    </TableRow>
  )
}

export function UsersPage() {
  const users = useUsers()
  const session = useSession()
  const updateUser = useUpdateUser()

  if (users.isPending) {
    return <ListSkeleton count={4} />
  }

  if (users.isError || !users.data) {
    return <ErrorState message={users.error?.message} onRetry={() => users.refetch()} />
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Who can access this dashboard, and with which role.</p>
        <CreateUserDialog />
      </div>

      <ApiErrorText error={updateUser.error} />

      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Username</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Active</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.data.map((user) => (
              <UserRow key={user.id} user={user} currentUserId={session.data?.id} />
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
