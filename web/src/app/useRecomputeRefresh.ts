// Keeps an eye on the server's background recompute from every page: health is polled while
// it runs (see useHealth), and once it finishes, everything new figures change is refetched.
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { RECOMPUTED_KEYS } from '../api/client'
import { useHealth } from '../api/settings'

export function useRecomputeRefresh() {
  const health = useHealth()
  const client = useQueryClient()
  const running = Boolean(health.data?.recompute)
  const wasRunning = useRef(false)
  useEffect(() => {
    if (wasRunning.current && !running) {
      for (const key of RECOMPUTED_KEYS) void client.invalidateQueries({ queryKey: [key] })
    }
    wasRunning.current = running
  }, [running, client])
}
