import { MessageCircle, MonitorCheck } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

type Actor = 'communeer' | 'whatsapp'

interface Step {
  actor: Actor
  title: string
  description: string
}

const STEPS: Step[] = [
  {
    actor: 'communeer',
    title: 'Select members to include',
    description:
      'Pick candidates from the suggestion list below (already excludes every admin) and start a round. Members who’ve never posted a message are listed first — a real signal, not a guess.',
  },
  {
    actor: 'whatsapp',
    title: 'Post the confirmation request yourself',
    description:
      'Communeer does not send anything. Open WhatsApp and post your own message asking members to react (e.g. 👍) if they still live here / want to stay.',
  },
  {
    actor: 'whatsapp',
    title: 'Members react or reply in WhatsApp',
    description: 'You watch for this yourself — Communeer cannot read reactions or replies.',
  },
  {
    actor: 'communeer',
    title: 'Mark them confirmed here',
    description: 'Every time you see a real reply, click "Mark confirmed" on that person’s row.',
  },
  {
    actor: 'communeer',
    title: 'After the deadline: review who’s left',
    description:
      'Anyone still pending moves into "Not confirmed" automatically — nothing to do, this is computed live, not a scheduled job.',
  },
  {
    actor: 'whatsapp',
    title: 'Remove them yourself, if you decide to',
    description:
      'Communeer never removes anyone. Review the list, then remove people in WhatsApp directly, on your own judgment.',
  },
]

const ACTOR_STYLE: Record<Actor, { icon: typeof MessageCircle; label: string; className: string }> = {
  communeer: {
    icon: MonitorCheck,
    label: 'Tracked in Communeer',
    className: 'border-primary/30 bg-primary/10 text-primary',
  },
  whatsapp: {
    icon: MessageCircle,
    label: 'You, in WhatsApp',
    className: 'border-warning/40 bg-warning/10 text-warning-foreground',
  },
}

export function RenewalHowItWorks() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">How renewals work</CardTitle>
        <p className="text-sm text-muted-foreground">
          A manual tracking flow, step by step — Communeer never sends a WhatsApp message, reads a reaction, or
          removes anyone on its own.
        </p>
      </CardHeader>
      <CardContent>
        <ol className="flex flex-col gap-0">
          {STEPS.map((step, index) => {
            const { icon: Icon, label, className } = ACTOR_STYLE[step.actor]
            const isLast = index === STEPS.length - 1
            return (
              <li key={step.title} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className="flex size-7 shrink-0 items-center justify-center rounded-full border bg-card text-xs font-semibold">
                    {index + 1}
                  </div>
                  {!isLast ? <div className="my-1 w-px flex-1 bg-border" /> : null}
                </div>
                <div className={cn('flex flex-col gap-1.5', isLast ? 'pb-0' : 'pb-5')}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium leading-tight">{step.title}</span>
                    <span
                      className={cn(
                        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
                        className,
                      )}
                    >
                      <Icon className="size-3" />
                      {label}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{step.description}</p>
                </div>
              </li>
            )
          })}
        </ol>
      </CardContent>
    </Card>
  )
}
