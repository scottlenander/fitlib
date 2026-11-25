import { missingRides } from '../api/client'
import { useDeleteRides } from '../api/rides'
import { missingText, rideCount } from '../library/bulkEdit'
import { ConfirmDialog } from '../shared/ConfirmDialog'

type Props = {
  // The rides to delete, with names to list (all of them up to a few, then a count).
  rides: { id: string; name: string }[]
  onDeleted: (count: number) => void
  onCancel: () => void
  // Some of the rides are gone already: the caller drops them (the dialog stays for the rest).
  onMissing?: (ids: string[]) => void
}

// How many ride names the dialog lists before summing up the rest.
const LISTED = 5

// Asks before deleting rides.
export function ConfirmDelete({ rides, onDeleted, onCancel, onMissing }: Props) {
  const remove = useDeleteRides()
  const count = rides.length
  const shown = rides.slice(0, LISTED)
  const more = count - shown.length

  return (
    <ConfirmDialog
      id="confirm-delete"
      title={`Delete ${count === 1 ? 'this ride' : rideCount(count)}?`}
      text={
        <>
          {count === 1
            ? "Its figures, notes, tags and recorded data are removed from fitlib, with the original file in fitlib's library. Your own copy of the file (in Zwift's or Garmin's folders) is kept, and importing it again skips the ride unless you ask."
            : "Their figures, notes, tags and recorded data are removed from fitlib, with the original files in fitlib's library. Your own copies of the files (in Zwift's or Garmin's folders) are kept, and importing them again skips the rides unless you ask."}{' '}
          This can't be undone.
        </>
      }
      error={
        remove.isError &&
        (onMissing && missingRides(remove.error).length
          ? missingText(missingRides(remove.error).length)
          : `Nothing was deleted: ${remove.error.message}`)
      }
      confirm={`Delete ${rideCount(count)}`}
      busyLabel="Deleting…"
      busy={remove.isPending}
      onCancel={onCancel}
      onConfirm={() =>
        remove.mutate(
          rides.map((r) => r.id),
          {
            onSuccess: (result) => onDeleted(result.deleted),
            onError: (error) => {
              const missing = missingRides(error)
              if (missing.length) onMissing?.(missing)
            },
          },
        )
      }
    >
      <ul data-testid="confirm-delete-rides">
        {shown.map((ride) => (
          <li key={ride.id}>{ride.name}</li>
        ))}
        {more > 0 && <li>and {rideCount(more)} more</li>}
      </ul>
    </ConfirmDialog>
  )
}
