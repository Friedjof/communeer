import { PanelLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { GroupSidebar } from './GroupSidebar'

interface CommunityShellProps {
  communityId: string
  currentGroupId?: string
  children: ReactNode
}

/** Two-column area rendered only inside /c/:id/* routes: GroupSidebar + content. */
export function CommunityShell({ communityId, currentGroupId, children }: CommunityShellProps) {
  const [mobileGroupsOpen, setMobileGroupsOpen] = useState(false)

  return (
    <div className="flex min-h-0 flex-1">
      <GroupSidebar communityId={communityId} currentGroupId={currentGroupId} className="hidden w-72 shrink-0 lg:flex" />

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <div className="border-b p-2 lg:hidden">
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setMobileGroupsOpen(true)}>
            <PanelLeft className="size-4" />
            Groups
          </Button>
        </div>
        <div className="flex-1 p-4 md:p-6">{children}</div>
      </div>

      <Sheet open={mobileGroupsOpen} onOpenChange={setMobileGroupsOpen}>
        <SheetContent side="left" className="w-80 p-0">
          <SheetHeader className="p-4 pb-0">
            <SheetTitle>Groups</SheetTitle>
          </SheetHeader>
          <GroupSidebar
            communityId={communityId}
            currentGroupId={currentGroupId}
            onNavigate={() => setMobileGroupsOpen(false)}
            className="border-r-0"
          />
        </SheetContent>
      </Sheet>
    </div>
  )
}
