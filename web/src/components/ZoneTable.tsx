import type { ZoneTime } from '../api/client'
import { duration } from '../format'

// Time in each zone, with a bar showing its share of the total.
export function ZoneTable({ title, zones }: { title: string; zones: ZoneTime[] }) {
  const total = zones.reduce((sum, z) => sum + z.seconds, 0) || 1
  return (
    <table className="zones" data-testid="zone-table">
      <caption>{title}</caption>
      <thead>
        <tr>
          <th scope="col">Zone</th>
          <th scope="col">Name</th>
          <th scope="col" className="num">
            Time
          </th>
          <th scope="col">Share</th>
        </tr>
      </thead>
      <tbody>
        {zones.map((zone) => {
          const share = Math.round((zone.seconds / total) * 100)
          return (
            <tr key={zone.zone}>
              <th scope="row">Z{zone.zone}</th>
              <td>{zone.name}</td>
              <td className="num">{duration(zone.seconds)}</td>
              <td className="share">
                <span className="bar" style={{ width: `${share}%` }} aria-hidden="true" />
                <span className="num">{share}%</span>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
