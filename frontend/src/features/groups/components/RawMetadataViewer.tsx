import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }

interface JsonNodeProps {
  label: string
  value: JsonValue
  depth: number
  defaultOpen: boolean
}

function isExpandable(value: JsonValue): value is JsonValue[] | Record<string, JsonValue> {
  return typeof value === 'object' && value !== null
}

function valuePreview(value: JsonValue): string {
  if (Array.isArray(value)) return `Array(${value.length})`
  if (value === null) return 'null'
  if (typeof value === 'object') return `Object(${Object.keys(value).length})`
  return ''
}

function ScalarValue({ value }: { value: JsonValue }) {
  if (value === null) return <span className="text-muted-foreground italic">null</span>
  if (typeof value === 'string') return <span className="text-primary">"{value}"</span>
  if (typeof value === 'boolean') return <span className="text-warning-foreground">{String(value)}</span>
  return <span className="text-foreground">{String(value)}</span>
}

function JsonNode({ label, value, depth, defaultOpen }: JsonNodeProps) {
  const [open, setOpen] = useState(defaultOpen)
  const expandable = isExpandable(value)

  if (!expandable) {
    return (
      <div className="flex items-start gap-1.5 py-0.5 font-mono text-xs" style={{ paddingLeft: depth * 16 }}>
        <span className="shrink-0 text-muted-foreground">{label}:</span>
        <ScalarValue value={value} />
      </div>
    )
  }

  const entries = Array.isArray(value) ? value.map((v, i) => [String(i), v] as const) : Object.entries(value)

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1 rounded py-0.5 font-mono text-xs transition-colors hover:bg-muted/60"
        style={{ paddingLeft: depth * 16 }}
      >
        <ChevronRight
          className={cn(
            'size-3.5 shrink-0 text-muted-foreground transition-transform duration-150',
            open && 'rotate-90',
          )}
        />
        <span className="text-muted-foreground">{label}:</span>
        {!open ? <span className="text-muted-foreground/70">{valuePreview(value)}</span> : null}
      </button>
      {open ? (
        <div>
          {entries.length === 0 ? (
            <p className="py-0.5 text-xs text-muted-foreground italic" style={{ paddingLeft: (depth + 1) * 16 }}>
              empty
            </p>
          ) : (
            entries.map(([key, childValue]) => (
              <JsonNode key={key} label={key} value={childValue} depth={depth + 1} defaultOpen={depth < 1} />
            ))
          )}
        </div>
      ) : null}
    </div>
  )
}

interface RawMetadataViewerProps {
  data: unknown
  className?: string
}

/** Hand-rolled recursive collapsible JSON tree — no library. */
export function RawMetadataViewer({ data, className }: RawMetadataViewerProps) {
  return (
    <div className={cn('overflow-x-auto rounded-lg border bg-muted/30 p-3', className)}>
      <JsonNode label="root" value={data as JsonValue} depth={0} defaultOpen={true} />
    </div>
  )
}
