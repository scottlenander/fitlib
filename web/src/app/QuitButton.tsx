import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useQuitServer } from '../api/app'
import { useHealth } from '../api/settings'
import { ConfirmDialog } from '../shared/ConfirmDialog'
import { useMarkStopped } from './quitContext'

// Stops fitlib, after asking. Only there when the server allows it: when the desktop
// launcher started it, not when it was started with `fitlib serve` in a terminal.
export function QuitButton() {
  const health = useHealth()
  const quit = useQuitServer()
  const client = useQueryClient()
  const markStopped = useMarkStopped()
  const [asking, setAsking] = useState(false)
  if (!health.data?.can_quit) return null

  return (
    <>
      <button
        type="button"
        className="quit-button"
        aria-label="Quit fitlib"
        onClick={() => setAsking(true)}
      >
        Quit
      </button>
      {asking && (
        <ConfirmDialog
          id="confirm-quit"
          title="Quit fitlib?"
          text="It stops importing from your watched folders and updating figures until you open it again."
          error={quit.isError && `fitlib didn't stop: ${quit.error.message}`}
          confirm="Quit"
          busyLabel="Quitting…"
          busy={quit.isPending}
          onCancel={() => setAsking(false)}
          onConfirm={() =>
            quit.mutate(undefined, {
              onSuccess: () => {
                // Nothing can load any more: stop asking, and show the stopped page.
                void client.cancelQueries()
                client.clear()
                markStopped()
              },
            })
          }
        />
      )}
    </>
  )
}
