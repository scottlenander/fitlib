// A small square in a compared ride's colour, next to its name: colour is never the only key.
export function Swatch({ index }: { index: number }) {
  return (
    <span
      className="swatch"
      aria-hidden="true"
      style={{ background: `var(--series-${index + 1})` }}
    />
  )
}

// The compared rides' line colours, read from the page's colour tokens (they differ in dark
// mode), in ride order.
export function seriesColours(count: number): string[] {
  const style = getComputedStyle(document.documentElement)
  return Array.from({ length: count }, (_, i) => style.getPropertyValue(`--series-${i + 1}`).trim())
}
