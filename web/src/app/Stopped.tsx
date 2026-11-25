import { useEffect } from 'react'

// Shown in place of the app once the Quit button has stopped the server.
export function Stopped() {
  useEffect(() => {
    document.title = 'fitlib (stopped)'
  }, [])
  return (
    <main id="main" className="stopped" data-testid="stopped">
      <h1>fitlib has stopped</h1>
      <p>
        Open it again from the Dock, or run <code>fitlib serve</code>.
      </p>
    </main>
  )
}
