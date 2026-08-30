import type { ReactNode } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface ModerationSectionCardProps {
  title: string
  description: string
  children: ReactNode
}

/** Shared `Card`/title/description/content shell used by every moderation
 * queue section — each section only supplies its own list (or empty-state
 * placeholder) as `children`. */
export function ModerationSectionCard({ title, description, children }: ModerationSectionCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}
