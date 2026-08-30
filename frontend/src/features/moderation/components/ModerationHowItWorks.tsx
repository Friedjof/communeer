import { ListChecks, MessageCircle, MonitorCheck } from 'lucide-react'
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
    title: 'Communeer scans data it has already synced',
    description:
      'Four sections below, each built from real signals already stored from past syncs — no new WhatsApp request is made to build this page.',
  },
  {
    actor: 'communeer',
    title: 'Review each flagged group or member',
    description: 'Click through to a group or member to see the exact number behind the flag before deciding anything.',
  },
  {
    actor: 'whatsapp',
    title: 'Act on it yourself, in WhatsApp',
    description:
      'Promote another admin, post in the group, or remove someone — Communeer never does any of this automatically. Same posture as renewals.',
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

export function ModerationHowItWorks() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">How the moderation queue works</CardTitle>
        <p className="text-sm text-muted-foreground">
          A candidate list only — Communeer never messages anyone, promotes/removes a member, or changes a group on
          its own.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
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

        <div className="flex gap-2 rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
          <ListChecks className="mt-0.5 size-4 shrink-0" />
          <p>
            Not detected here: per-member message-frequency or spam-burst detection, and duplicate/repeated-content
            detection. Both would need a real message history or counter, and only each member&apos;s{' '}
            <em>latest</em> activity is stored — an honest limit, not an oversight.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
