import { describe, expect, it } from 'vitest'
import type { Health } from '../api/settings'
import { outdatedNotice } from './outdated'

const HEALTH: Health = {
  status: 'ok',
  version: '0.1.0',
  rides: 120,
  outdated_rides: 0,
  recompute: null,
  build: 'abcdef123456',
  can_quit: false,
}

describe('outdatedNotice', () => {
  it('says nothing when every ride is current', () => {
    expect(outdatedNotice(HEALTH)).toBeNull()
    expect(outdatedNotice(undefined)).toBeNull()
  })

  it('shows the progress while the server updates rides', () => {
    const notice = outdatedNotice({
      ...HEALTH,
      outdated_rides: 80,
      recompute: { total: 120, done: 40 },
    })
    expect(notice).toEqual({
      kind: 'updating',
      done: 40,
      total: 120,
      text: 'Updating figures after an update: 40 of 120 rides.',
    })
  })

  it('says "ride" for a single ride', () => {
    const notice = outdatedNotice({ ...HEALTH, recompute: { total: 1, done: 0 } })
    expect(notice?.kind === 'updating' && notice.text).toBe(
      'Updating figures after an update: 0 of 1 ride.',
    )
  })

  it('counts the rides left once the update has stopped', () => {
    expect(outdatedNotice({ ...HEALTH, outdated_rides: 3 })).toEqual({
      kind: 'outdated',
      count: 3,
    })
  })
})
