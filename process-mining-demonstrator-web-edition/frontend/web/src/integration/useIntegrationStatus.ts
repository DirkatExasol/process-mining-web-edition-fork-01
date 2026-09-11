/** Polls the abstraction layer's live status (and the registered-extractor list) for
 *  the integration console. One interval feeds both the pipeline canvas and the status
 *  details, so the whole console reflects any import — manual, watchdog or API-pushed —
 *  as it happens. Re-polls immediately when the active connection changes (the target
 *  schema follows it). */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { IntegrationStatus } from '../types'

export function useIntegrationStatus(pollMs = 1500) {
  const store = useStore()
  const [status, setStatus] = useState<IntegrationStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const s = await api.integrationStatus()
        if (!alive) return
        setStatus(s)
        setError(null)
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err))
      }
    }
    void tick()
    const id = window.setInterval(tick, pollMs)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [store.connection.isConnected, store.connection.activeProfileId, pollMs])

  return { status, error }
}
