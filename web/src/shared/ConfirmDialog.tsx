import { useEffect, useRef, type ReactNode } from 'react'

type Props = {
  // Prefix for the heading's and text's ids (`<id>-heading`, `<id>-text`).
  id: string
  title: string
  // What happens, as the dialog's description (in a paragraph with the text id).
  text: ReactNode
  // Shown between the title and the text, such as the rides to delete.
  children?: ReactNode
  // An error from the last try, shown above the buttons.
  error?: ReactNode
  confirm: string
  // Label while the action runs; both buttons are disabled meanwhile.
  busyLabel: string
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
}

// Asks before doing something that can't be taken back, in a modal dialog. Cancel has the
// focus, so pressing Enter straight away never confirms; Escape cancels too, unless the
// action is already running.
export function ConfirmDialog(props: Props) {
  const { id, title, text, children, error, confirm, busyLabel, busy, onConfirm, onCancel } = props
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
    return () => dialog?.close()
  }, [])

  return (
    <dialog
      ref={ref}
      className="confirm-dialog"
      aria-labelledby={`${id}-heading`}
      aria-describedby={`${id}-text`}
      onCancel={(event) => {
        event.preventDefault()
        if (!busy) onCancel()
      }}
    >
      <h2 id={`${id}-heading`}>{title}</h2>
      {children}
      <p id={`${id}-text`}>{text}</p>
      {error && (
        <p role="alert" data-testid="form-error">
          {error}
        </p>
      )}
      <div className="button-row">
        <button type="button" autoFocus disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="danger" disabled={busy} onClick={onConfirm}>
          {busy ? busyLabel : confirm}
        </button>
      </div>
    </dialog>
  )
}
