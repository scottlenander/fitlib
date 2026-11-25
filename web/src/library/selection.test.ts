// Selecting rides in the library, and the stored selection.
import { describe, expect, test } from 'vitest'
import { MAX_SELECTED, readPicked, selectAll, toggle, unselectAll, type Picked } from './selection'

const ride = (n: number): Picked => ({ id: `id-${n}`, name: `Ride ${n}` })
const rides = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, i) => ride(from + i))

describe('selecting rides', () => {
  test('selecting adds a ride and selecting it again takes it out', () => {
    const once = toggle([], ride(1))

    expect(once).toEqual([ride(1)])
    expect(toggle(once, ride(1))).toEqual([])
  })

  test('more than four rides can be selected, up to the limit', () => {
    const full = rides(1, MAX_SELECTED)

    expect(toggle(rides(1, 4), ride(5))).toHaveLength(5)
    expect(toggle(full, ride(MAX_SELECTED + 1))).toBe(full)
  })

  test('a whole page is added once each, after what is already selected', () => {
    expect(selectAll([ride(3)], rides(1, 4)).map((p) => p.id)).toEqual([
      'id-3',
      'id-1',
      'id-2',
      'id-4',
    ])
  })

  test('selecting a page stops at the limit', () => {
    expect(selectAll(rides(1, MAX_SELECTED - 1), rides(1000, 1009))).toHaveLength(MAX_SELECTED)
  })

  test('unselecting a page leaves rides from other pages', () => {
    expect(unselectAll(rides(1, 5), rides(2, 3)).map((p) => p.id)).toEqual(['id-1', 'id-4', 'id-5'])
  })
})

describe('stored selection', () => {
  test('a stored list reads back', () => {
    expect(readPicked(() => JSON.stringify([ride(1), ride(2)]))).toEqual([ride(1), ride(2)])
  })

  test.each([
    ['nothing stored', null],
    ['not JSON', '{'],
    ['not a list', '{"id": "x"}'],
  ])('%s reads as no rides', (_, stored) => {
    expect(readPicked(() => stored)).toEqual([])
  })

  test('entries that are not rides are dropped', () => {
    const stored = JSON.stringify([ride(1), { id: 2 }, 'x', ride(3)])

    expect(readPicked(() => stored).map((p) => p.id)).toEqual(['id-1', 'id-3'])
  })

  test('no more than the limit is read back', () => {
    expect(readPicked(() => JSON.stringify(rides(1, MAX_SELECTED + 3)))).toHaveLength(MAX_SELECTED)
  })

  test('blocked storage reads as no rides', () => {
    expect(
      readPicked(() => {
        throw new Error('blocked')
      }),
    ).toEqual([])
  })
})
