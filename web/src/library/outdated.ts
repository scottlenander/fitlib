// What the library says about rides computed with older calculations.
import type { Health } from '../api/settings'

export type OutdatedNotice =
  | { kind: 'updating'; done: number; total: number; text: string }
  | { kind: 'outdated'; count: number }

// The server is updating them (with progress), or some are left (the update is off, or
// some rides couldn't be updated): run `fitlib recompute`. Nothing when all are current.
export function outdatedNotice(health: Health | undefined): OutdatedNotice | null {
  if (!health) return null
  const job = health.recompute
  if (job) {
    const rides = job.total === 1 ? 'ride' : 'rides'
    return {
      kind: 'updating',
      done: job.done,
      total: job.total,
      text: `Updating figures after an update: ${job.done} of ${job.total} ${rides}.`,
    }
  }
  return health.outdated_rides > 0 ? { kind: 'outdated', count: health.outdated_rides } : null
}
