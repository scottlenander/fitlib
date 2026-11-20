// What the library's "Edit rides" form sends.
import { describe, expect, test } from 'vitest'
import { KEEP_ALL, bulkChange, rideCount } from './bulkEdit'

describe('bulk change', () => {
  test('a form left as it is changes nothing', () => {
    expect(bulkChange(KEEP_ALL)).toBeNull()
    expect(bulkChange({ ...KEEP_ALL, add: ' , ' })).toBeNull()
  })

  test('an effort and bike are set; kept fields are left out', () => {
    expect(bulkChange({ ...KEEP_ALL, effort: '7', bike: 'b1' })).toEqual({
      rpe: 7,
      bike_id: 'b1',
      add_tags: [],
      remove_tags: [],
    })
  })

  test('clearing sends null', () => {
    expect(bulkChange({ ...KEEP_ALL, effort: 'clear', bike: 'none' })).toEqual({
      rpe: null,
      bike_id: null,
      add_tags: [],
      remove_tags: [],
    })
  })

  test('tags to add and remove are split on commas', () => {
    expect(bulkChange({ ...KEEP_ALL, add: 'Cobbles, wet', remove: 'z2' })).toEqual({
      add_tags: ['Cobbles', 'wet'],
      remove_tags: ['z2'],
    })
  })
})

test('ride counts', () => {
  expect(rideCount(1)).toBe('1 ride')
  expect(rideCount(12)).toBe('12 rides')
})
