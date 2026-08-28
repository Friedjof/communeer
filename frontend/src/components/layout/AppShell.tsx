import type { ReactNode } from 'react'
import { useState } from 'react'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { MainNavigation } from './MainNavigation'
import { Topbar } from './Topbar'

interface AppShellProps {
  communityId?: string
  children: ReactNode
}

export function AppShell({ communityId, children }: AppShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="flex h-svh flex-col">
      <Topbar communityId={communityId} onOpenMobileNav={() => setMobileNavOpen(true)} />

      <div className="hidden border-b bg-card px-4 py-1.5 lg:block">
        <MainNavigation communityId={communityId} />
      </div>

      <main className="flex min-h-0 flex-1 flex-col">{children}</main>

      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="w-72">
          <SheetHeader>
            <SheetTitle>Menu</SheetTitle>
          </SheetHeader>
          <div className="px-2">
            <MainNavigation
              communityId={communityId}
              className="flex-col items-stretch"
              onNavigate={() => setMobileNavOpen(false)}
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
