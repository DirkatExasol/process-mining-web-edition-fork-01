/** Auto sign-out on inactivity.
 *
 * When the admin has configured an idle timeout (Users page) and the surface requires
 * sign-in, this watches for user activity and signs the user out after that many
 * idle minutes. It also pings the session endpoint on activity (throttled) so the
 * server's *sliding* session stays alive while the user is active but not making
 * API calls; a truly idle session expires on both sides. Renders nothing.
 *
 * `alwaysRequireAuth` forces the "requires sign-in" side on regardless of the global
 * `requireLogin` setting — used by the integration console, which is always role-gated
 * even when the main app is open to anonymous access. */

import { useEffect, useRef } from 'react'
import { useStore } from '../store'

const ACTIVITY_EVENTS = [
  'mousemove',
  'mousedown',
  'keydown',
  'touchstart',
  'scroll',
  'wheel',
] as const

export function IdleLogout({ alwaysRequireAuth = false }: { alwaysRequireAuth?: boolean } = {}) {
  const idleMins = useStore((s) => s.idleTimeoutMins)
  const enabled = useStore(
    (s) => (alwaysRequireAuth || s.requireLogin) && !!s.authUser && s.idleTimeoutMins > 0,
  )
  const lastActivity = useRef(Date.now())
  const lastPing = useRef(0)

  useEffect(() => {
    if (!enabled) return
    const idleMs = idleMins * 60_000
    // Refresh the server session at most this often while the user is active.
    const pingEvery = Math.min(60_000, Math.max(15_000, idleMs / 3))
    lastActivity.current = Date.now()

    const onActivity = () => {
      const now = Date.now()
      lastActivity.current = now
      if (now - lastPing.current > pingEvery) {
        lastPing.current = now
        // GET /auth/session slides the server-side idle window (see frontend/server.py).
        void fetch('/auth/session').catch(() => {})
      }
    }
    for (const ev of ACTIVITY_EVENTS)
      window.addEventListener(ev, onActivity, { passive: true })

    // Poll a few times per idle window; on wake-from-background the elapsed check
    // still catches an expired session even if timers were throttled.
    const tick = Math.min(15_000, Math.max(2_000, idleMs / 6))
    const interval = window.setInterval(() => {
      if (Date.now() - lastActivity.current >= idleMs) {
        void useStore.getState().logout({ inactivity: true })
      }
    }, tick)

    return () => {
      for (const ev of ACTIVITY_EVENTS) window.removeEventListener(ev, onActivity)
      window.clearInterval(interval)
    }
  }, [enabled, idleMins])

  return null
}
