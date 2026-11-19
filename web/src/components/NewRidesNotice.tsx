import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { NEW_RIDE_KEYS, useWatch } from '../api/client'

// Under the header on every page: says when the server's watcher has imported new rides
// since this page was opened, and refreshes the lists and charts they change. Rides imported
// before the page loaded aren't "new". The status region is always there, so screen readers
// announce the message when it appears.
export function NewRidesNotice() {
  const watch = useWatch()
  const client = useQueryClient()
  const current = watch.data?.last_import ?? null
  // The last import already shown (or dismissed); undefined until the first answer.
  const [seen, setSeen] = useState<string | null | undefined>(undefined)
  if (watch.data && seen === undefined) setSeen(current)

  // Refetch what new rides change, once per new import.
  const refreshed = useRef<string | null | undefined>(undefined)
  useEffect(() => {
    if (!watch.data) return
    if (refreshed.current !== undefined && current !== refreshed.current) {
      for (const key of NEW_RIDE_KEYS) void client.invalidateQueries({ queryKey: [key] })
    }
    refreshed.current = current
  }, [watch.data, current, client])

  const fresh =
    seen !== undefined && current !== seen
      ? (watch.data?.recent ?? []).filter(
          (f) => f.outcome === 'imported' && (seen === null || f.seen_at > seen),
        )
      : []
  return (
    <div role="status" className="new-rides">
      {fresh.length > 0 && (
        <p className="notice" data-testid="new-rides-notice">
          {fresh.length === 1
            ? '1 new ride imported from a watched folder.'
            : `${fresh.length} new rides imported from watched folders.`}{' '}
          {fresh.length === 1 && fresh[0]!.ride_id ? (
            <Link to={`/rides/${fresh[0]!.ride_id}`}>Open it</Link>
          ) : (
            <Link to="/">Open the library</Link>
          )}{' '}
          <button type="button" onClick={() => setSeen(current)}>
            Dismiss
          </button>
        </p>
      )}
    </div>
  )
}
