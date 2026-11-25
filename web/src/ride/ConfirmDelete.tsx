import { useEffect, useRef } from 'react'
import { missingRides } from '../api/client'
import { useDeleteRides } from '../api/rides'
import { missingText, rideCount } from '../library/bulkEdit'

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

// Asks before deleting rides, in a modal dialog. Cancel has the focus, so pressing Enter
// straight away never deletes; Escape cancels too.
export function ConfirmDelete({ rides, onDeleted, onCancel, onMissing }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const remove = useDeleteRides()
  const count = rides.length

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
    return () => dialog?.close()
  }, [])

  const shown = rides.slice(0, LISTED)
  const more = count - shown.length

  return (
    <dialog
      ref={ref}
      className="confirm-dialog"
      aria-labelledby="confirm-delete-heading"
      aria-describedby="confirm-delete-text"
      onCancel={(event) => {
        event.preventDefault()
        if (!remove.isPending) onCancel()
      }}
    >
      <h2 id="confirm-delete-heading">Delete {count === 1 ? 'this ride' : rideCount(count)}?</h2>
      <ul data-testid="confirm-delete-rides">
        {shown.map((ride) => (
          <li key={ride.id}>{ride.name}</li>
        ))}
        {more > 0 && <li>and {rideCount(more)} more</li>}
      </ul>
      <p id="confirm-delete-text">
        {count === 1
          ? "Its figures, notes, tags and recorded data are removed from fitlib, with the original file in fitlib's library. Your own copy of the file (in Zwift's or Garmin's folders) is kept, and importing it again skips the ride unless you ask."
          : "Their figures, notes, tags and recorded data are removed from fitlib, with the original files in fitlib's library. Your own copies of the files (in Zwift's or Garmin's folders) are kept, and importing them again skips the rides unless you ask."}{' '}
        This can't be undone.
      </p>
      {remove.isError && (
        <p role="alert" data-testid="form-error">
          {onMissing && missingRides(remove.error).length
            ? missingText(missingRides(remove.error).length)
            : `Nothing was deleted: ${remove.error.message}`}
        </p>
      )}
      <div className="button-row">
        <button type="button" autoFocus disabled={remove.isPending} onClick={onCancel}>
          Cancel
        </button>
        <button
          type="button"
          className="danger"
          disabled={remove.isPending}
          onClick={() =>
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
          {remove.isPending ? 'Deleting…' : `Delete ${rideCount(count)}`}
        </button>
      </div>
    </dialog>
  )
}
