// A group of labelled figures ("Distance: 19.9 mi"), shown as cards.
export type Stat = { label: string; value: string; note?: string }

export function Stats({ stats, testId }: { stats: Stat[]; testId: string }) {
  return (
    <dl className="stats" data-testid={testId}>
      {stats.map((stat) => (
        <div key={stat.label} className="stat" data-testid="stat">
          <dt>{stat.label}</dt>
          <dd>
            {stat.value}
            {stat.note && <span className="stat-note"> {stat.note}</span>}
          </dd>
        </div>
      ))}
    </dl>
  )
}
