// What the library says about rides that went: deleted here or from a ride's page, and
// selected rides found gone (deleted in another tab or the command line).
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import type { DeletedState } from '../ride/RideDetails'
import { missingText, rideCount } from './bulkEdit'
import type { Picked } from './selection'

type Selection = { picked: Picked[]; unselectAll: (rides: Picked[]) => void }

export function useLibraryNotices(selection: Selection) {
  // "Deleted …" from a ride's page comes as navigation state: read once, then cleared from
  // the history entry, so a reload or Back doesn't say it again.
  const location = useLocation()
  const navigate = useNavigate()
  const [fromRide] = useState(() => (location.state as DeletedState | null)?.deleted)
  useEffect(() => {
    if ((location.state as DeletedState | null)?.deleted)
      void navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [location, navigate])
  const [deletedHere, setDeletedHere] = useState<string | null>(null)
  const [missingNotice, setMissingNotice] = useState<string | null>(null)

  return {
    deletedNotice: deletedHere ?? (fromRide ? `Deleted ${fromRide}.` : null),
    missingNotice,
    // Selected rides that turned out to be gone: unselected, and said so.
    dropMissing: (ids: string[]) => {
      const gone = new Set(ids)
      selection.unselectAll(selection.picked.filter((p) => gone.has(p.id)))
      setMissingNotice(missingText(ids.length))
    },
    // Rides deleted from the selection bar.
    deleted: (count: number) => {
      setDeletedHere(`Deleted ${rideCount(count)}.`)
    },
  }
}
