import { ChevronDown, MessageCircle, MonitorCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

type Actor = 'communeer' | 'automated' | 'whatsapp'

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
    actor: 'automated',
    title: 'A reminder goes out immediately',
    description:
      'Communeer sends each selected member a bilingual (German/English) direct message explaining how to confirm or opt out — no manual posting needed.',
  },
  {
    actor: 'whatsapp',
    title: 'Members react or reply in WhatsApp',
    description: 'They react 👍 to stay, ❌ to leave, or just reply in plain text.',
  },
  {
    actor: 'automated',
    title: '👍 and ❌ are read automatically',
    description:
      'A reaction updates their status the moment it happens — 👍 confirms, ❌ is treated as an immediate decline, without waiting for the deadline. A plain text reply still needs a human to read it.',
  },
  {
    actor: 'communeer',
    title: 'Mark replies confirmed, or check reactions any time',
    description:
      'Click "Mark confirmed" for a text reply you saw yourself, or "Check reactions" to actively ask WhatsApp right now instead of waiting on the automatic check.',
  },
  {
    actor: 'communeer',
    title: 'After the deadline: review who’s left',
    description:
      'Anyone still pending (or already declined via ❌) moves into "Not confirmed" automatically — nothing to do, this is computed live, not a scheduled job.',
  },
  {
    actor: 'communeer',
    title: 'Click "Process removals" when you\'re ready',
    description:
      'Removes everyone currently declined or past the deadline from this one group in a single batch — nothing is ever removed automatically, this is always a deliberate click.',
  },
  {
    actor: 'communeer',
    title: 'Or just take them off this list',
    description: 'Use "Remove" on a row to stop tracking someone here — this never touches WhatsApp itself.',
  },
]

const ACTOR_STYLE: Record<Actor, { icon: typeof MessageCircle; label: string; className: string }> = {
  communeer: {
    icon: MonitorCheck,
    label: 'You, in Communeer',
    className: 'border-border bg-muted text-foreground',
  },
  automated: {
    icon: Sparkles,
    label: 'Automated by Communeer',
    className: 'border-primary/30 bg-primary/10 text-primary',
  },
  whatsapp: {
    icon: MessageCircle,
    label: 'In WhatsApp',
    className: 'border-warning/40 bg-warning/10 text-warning-foreground',
  },
}

export function RenewalHowItWorks() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div>
          <CardTitle className="text-base">How renewals work</CardTitle>
          <p className="text-sm text-muted-foreground">
            A mostly-automated flow: Communeer sends the reminder and reads 👍/❌ reactions on its own; replying and
            actually removing someone from this group are still a deliberate click.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5 shrink-0"
          aria-expanded={isOpen}
          onClick={() => setIsOpen((open) => !open)}
        >
          {isOpen ? 'Hide' : 'Show steps'}
          <ChevronDown className={cn('size-4 transition-transform', isOpen ? 'rotate-180' : '')} />
        </Button>
      </CardHeader>
      {isOpen ? (
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
      ) : null}
    </Card>
  )
}
