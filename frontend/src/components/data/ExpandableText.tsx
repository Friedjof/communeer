import { type ReactNode, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

const DEFAULT_MAX_LENGTH = 220

// WhatsApp's own inline markup (single `*bold*`, `_italic_`, `~strikethrough~`)
// shows up verbatim in group/community descriptions pulled from the real
// WhatsApp API — render it instead of leaving the raw asterisks/underscores
// visible, since that's what looked "off" about unformatted descriptions.
const INLINE_MARKUP = /\*(.+?)\*|_(.+?)_|~(.+?)~/g

function renderInlineMarkup(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  let i = 0

  INLINE_MARKUP.lastIndex = 0
  while ((match = INLINE_MARKUP.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }
    const key = `${keyPrefix}-${i++}`
    if (match[1] !== undefined) nodes.push(<strong key={key}>{match[1]}</strong>)
    else if (match[2] !== undefined) nodes.push(<em key={key}>{match[2]}</em>)
    else if (match[3] !== undefined) nodes.push(<del key={key}>{match[3]}</del>)
    lastIndex = INLINE_MARKUP.lastIndex
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}

interface ExpandableTextProps {
  text: string | null
  title?: string
  maxLength?: number
  emptyLabel?: string
  className?: string
}

/**
 * Renders a description with WhatsApp's inline markup and real line breaks
 * preserved (`whitespace-pre-wrap` — a plain `<p>` collapses the `\n\n`s
 * WhatsApp descriptions actually contain into a single run-on line).
 * Truncates to `maxLength` with a "More" button that opens the full text in
 * a dialog, rather than dumping potentially very long descriptions inline.
 */
export function ExpandableText({
  text,
  title = 'Description',
  maxLength = DEFAULT_MAX_LENGTH,
  emptyLabel = 'No description.',
  className,
}: ExpandableTextProps) {
  const [open, setOpen] = useState(false)

  if (!text) {
    return <p className={cn('text-muted-foreground', className)}>{emptyLabel}</p>
  }

  const isTruncated = text.length > maxLength
  const preview = isTruncated ? `${text.slice(0, maxLength).trimEnd()}…` : text

  return (
    <>
      <p className={cn('whitespace-pre-wrap', className)}>
        {renderInlineMarkup(preview, 'preview')}
        {isTruncated ? (
          <>
            {' '}
            <Button variant="link" className="h-auto p-0 align-baseline" onClick={() => setOpen(true)}>
              More
            </Button>
          </>
        ) : null}
      </p>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription className="sr-only">Full text.</DialogDescription>
          </DialogHeader>
          <p className="whitespace-pre-wrap text-sm">{renderInlineMarkup(text, 'full')}</p>
        </DialogContent>
      </Dialog>
    </>
  )
}
