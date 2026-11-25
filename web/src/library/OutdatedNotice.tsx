import type { Health } from '../api/settings'
import { outdatedNotice } from './outdated'

// Rides computed with older calculations: the server's progress updating them, or how to
// update those left. The status region is always there, so progress is announced.
export function OutdatedNotice({ health }: { health: Health | undefined }) {
  const notice = outdatedNotice(health)
  return (
    <div role="status">
      {notice?.kind === 'updating' && (
        <div className="notice" data-testid="outdated-notice">
          <p id="recompute-progress">{notice.text}</p>
          <progress aria-labelledby="recompute-progress" value={notice.done} max={notice.total} />
        </div>
      )}
      {notice?.kind === 'outdated' && (
        <p className="notice" data-testid="outdated-notice">
          {notice.count} {notice.count === 1 ? 'ride was' : 'rides were'} computed with older
          calculations. Run <code>fitlib recompute</code> to bring{' '}
          {notice.count === 1 ? 'it' : 'them'} up to date.
        </p>
      )}
    </div>
  )
}
