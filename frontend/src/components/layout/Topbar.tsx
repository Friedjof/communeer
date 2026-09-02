import { useNavigate } from '@tanstack/react-router'
import { LogOut, Menu, Monitor, Moon, Sun } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { CommunitySelector } from '@/features/communities/components/CommunitySelector'
import { useLogout, useSession } from '@/features/auth/queries'
import { ConnectionBadge } from '@/features/whatsapp/components/ConnectionBadge'
import { useWhatsAppStatus } from '@/features/whatsapp/queries'
import { initials } from '@/lib/format'
import { type Theme, useUiStore } from '@/lib/uiStore'

interface TopbarProps {
  communityId?: string
  onOpenMobileNav: () => void
}

export function Topbar({ communityId, onOpenMobileNav }: TopbarProps) {
  const session = useSession()
  const logout = useLogout()
  const navigate = useNavigate()
  const whatsapp = useWhatsAppStatus()
  const theme = useUiStore((state) => state.theme)
  const setTheme = useUiStore((state) => state.setTheme)

  function handleLogout() {
    logout.mutate(undefined, {
      onSuccess: () => {
        void navigate({ to: '/login' })
      },
    })
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-card px-4">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onOpenMobileNav} aria-label="Open navigation">
        <Menu className="size-5" />
      </Button>

      <a href="/" className="flex items-center gap-2 font-semibold">
        <img src="/logo.png" alt="" className="size-7" />
        <span className="hidden sm:inline">Communeer</span>
      </a>

      <CommunitySelector currentCommunityId={communityId} />

      <ConnectionBadge state={whatsapp.data?.state ?? 'connecting'} className="ml-auto hidden sm:flex" />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="ml-2 gap-2 px-1.5">
            <Avatar className="size-7">
              <AvatarFallback className="text-xs">{session.data ? initials(session.data.username) : '?'}</AvatarFallback>
            </Avatar>
            <span className="hidden text-sm font-medium sm:inline">{session.data?.username}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuLabel>Theme</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={theme} onValueChange={(value) => setTheme(value as Theme)}>
            <DropdownMenuRadioItem value="light">
              <Sun className="size-4" />
              Light
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark">
              <Moon className="size-4" />
              Dark
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="system">
              <Monitor className="size-4" />
              System
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-destructive transition-colors hover:bg-muted"
          >
            <LogOut className="size-4" />
            Log out
          </button>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
