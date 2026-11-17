import type { ReactNode } from 'react'

// A box a wide table scrolls sideways in on a narrow screen. It can be reached with Tab and
// is named after its table, so keyboard users can scroll it with the arrow keys; use it for
// tables with nothing else to Tab to (tables with links are reachable through them).
export function ScrollBox({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="table-scroll" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  )
}
