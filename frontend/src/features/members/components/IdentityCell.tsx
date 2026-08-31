import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { initials } from '@/lib/format'

export function IdentityCell({
  avatarUrl,
  displayName,
  waId,
}: {
  avatarUrl: string | null
  displayName: string
  waId: string
}) {
  return (
    <div className="flex items-center gap-2.5">
      <Avatar className="size-8">
        {avatarUrl ? <AvatarImage src={avatarUrl} alt="" /> : null}
        <AvatarFallback className="text-xs">{initials(displayName)}</AvatarFallback>
      </Avatar>
      <div className="flex flex-col">
        <span className="font-medium leading-tight">{displayName}</span>
        <span className="text-xs text-muted-foreground leading-tight">{waId}</span>
      </div>
    </div>
  )
}
