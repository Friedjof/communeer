import { useEffect, useRef, useState } from 'react'

/** Animates a number counting up from its previous value to `target` over
 * `durationMs`, via `requestAnimationFrame` (not a CSS transition — you
 * can't transition the text content of a number). Jumps straight to
 * `target` for users who've asked for reduced motion, since this is a
 * JS-driven animation the global CSS reduced-motion override can't reach. */
export function useCountUp(target: number, durationMs = 600): number {
  const [value, setValue] = useState(0)
  const fromRef = useRef(0)

  useEffect(() => {
    // Guarded: this test suite's jsdom environment doesn't implement
    // `matchMedia` at all (unlike real browsers) — treat "unavailable" the
    // same as "no preference expressed", not as a crash.
    const prefersReducedMotion =
      typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReducedMotion || fromRef.current === target) {
      setValue(target)
      fromRef.current = target
      return
    }

    const from = fromRef.current
    const startTime = performance.now()
    let frame: number

    function tick(now: number) {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / durationMs, 1)
      // ease-out cubic — starts fast, settles gently, matches this app's
      // other "ease-out" motion (e.g. `CapacityBar`'s fill-in).
      const eased = 1 - (1 - progress) ** 3
      setValue(Math.round(from + (target - from) * eased))
      if (progress < 1) {
        frame = requestAnimationFrame(tick)
      }
    }

    frame = requestAnimationFrame(tick)
    fromRef.current = target
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])

  return value
}
