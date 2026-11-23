import { useEffect, useRef } from 'react'

// Background checks (heartbeat, notification bell, live banner) used to run on
// a fixed timer in every open tab, even tabs left hidden all day. This hook
// runs them only while someone can see the page:
//   - runs `fn` once straight away (or when first shown, for a background tab)
//   - repeats every `intervalMs` while the tab is visible
//   - stops while the tab is hidden, and runs again as soon as it's shown
//     (if a tick was missed), so nothing looks stale when you come back
//   - after `idleMs` with no mouse/keyboard/touch/scroll, slows to
//     `idleIntervalMs` (pass 0 to stop entirely while idle); any input wakes
//     it up and runs `fn` again if it's overdue
export const ACTIVITY_EVENTS = ['pointerdown', 'pointermove', 'keydown', 'scroll', 'touchstart', 'wheel']

export function isPageVisible() {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden'
}

export default function usePolling(fn, intervalMs, {
  enabled = true,
  idleMs = 10 * 60 * 1000,
  idleIntervalMs = 5 * 60 * 1000,
  deps = [],
} = {}) {
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) return undefined
    let lastRun = 0
    let lastActivity = Date.now()
    let timer = null

    const isIdle = () => idleMs > 0 && Date.now() - lastActivity >= idleMs
    const currentInterval = () => (isIdle() ? idleIntervalMs : intervalMs)

    const run = () => {
      lastRun = Date.now()
      try { fnRef.current() } catch { /* a failed check never breaks the page */ }
    }

    const schedule = () => {
      clearTimeout(timer)
      timer = null
      if (!isPageVisible()) return
      const every = currentInterval()
      if (!every) return
      const wait = Math.max(0, lastRun + every - Date.now())
      timer = setTimeout(() => {
        if (isPageVisible()) run()
        schedule()
      }, wait)
    }

    const wake = () => {
      if (!isPageVisible()) { clearTimeout(timer); timer = null; return }
      if (Date.now() - lastRun >= intervalMs) run()
      schedule()
    }

    const onActivity = () => {
      const wasIdle = isIdle()
      lastActivity = Date.now()
      if (wasIdle) wake()
    }
    // Coming back to the tab counts as activity
    const onVisibility = () => { if (isPageVisible()) lastActivity = Date.now(); wake() }

    // A tab opened in the background waits until it's first shown
    if (isPageVisible()) run()
    schedule()
    document.addEventListener('visibilitychange', onVisibility)
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, onActivity, { passive: true }))
    return () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, onActivity))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, intervalMs, idleMs, idleIntervalMs, ...deps])
}
