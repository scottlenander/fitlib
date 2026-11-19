import type { ReactNode } from 'react'

// A chart's numbers as a table, folded away until asked for. The hidden part of the summary
// names the table, so each "Show table" is told apart by screen readers.
export function ShowTable({ name, children }: { name: string; children: ReactNode }) {
  return (
    <details className="show-table">
      <summary>
        Show table<span className="visually-hidden">: {name}</span>
      </summary>
      {children}
    </details>
  )
}
