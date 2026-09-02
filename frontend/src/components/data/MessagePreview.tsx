/** Read-only, line-break-preserving rendering of an outgoing WhatsApp
 * message's exact text — used by every send-confirmation dialog so an admin
 * sees precisely what a recipient will get before triggering the send. */
export function MessagePreview({ text }: { text: string }) {
  return (
    <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg border bg-muted/40 p-3 font-sans text-sm">
      {text}
    </pre>
  )
}
