import type { ReactElement } from 'react'
import { useId } from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

interface HelpTooltipProps {
  content: string
  children: ReactElement
}

/** Wraps a single trigger element in a real hover-help tooltip, wiring `aria-describedby` so screen readers announce the help text too. */
export function HelpTooltip({ content, children }: HelpTooltipProps) {
  const id = useId()
  return (
    <Tooltip>
      <TooltipTrigger asChild aria-describedby={id}>
        {children}
      </TooltipTrigger>
      <TooltipContent id={id}>{content}</TooltipContent>
    </Tooltip>
  )
}
