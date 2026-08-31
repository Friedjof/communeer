import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { initials } from '@/lib/format'

export function MemberIdentity({ displayName, waId }: { displayName: string; waId: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <Avatar className="size-8">
        <AvatarFallback className="text-xs">{initials(displayName)}</AvatarFallback>
      </Avatar>
      <div className="flex flex-col">
        <span className="font-medium leading-tight">{displayName}</span>
        <span className="text-xs text-muted-foreground leading-tight">{waId}</span>
      </div>
    </div>
  )
}
