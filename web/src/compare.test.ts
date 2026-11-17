// Picking rides to compare and the compare page's address.
import { describe, expect, test } from 'vitest'
import { compareUrl, parseIds, readPicked, toggle, type Picked } from './compare'

const ride = (n: number): Picked => ({ id: `id-${n}`, name: `Ride ${n}` })

describe('picking rides', () => {
  test('picking adds a ride and picking it again takes it out', () => {
    const once = toggle([], ride(1))

    expect(once).toEqual([ride(1)])
    expect(toggle(once, ride(1))).toEqual([])
  })

  test('nothing is added past four rides', () => {
    const four = [1, 2, 3, 4].map(ride)

    expect(toggle(four, ride(5))).toBe(four)
    expect(toggle(four, ride(2)).map((p) => p.id)).toEqual(['id-1', 'id-3', 'id-4'])
  })
})

describe('stored picks', () => {
  test('a stored list reads back', () => {
    expect(readPicked(() => JSON.stringify([ride(1), ride(2)]))).toEqual([ride(1), ride(2)])
  })

  test.each([
    ['nothing stored', null],
    ['not JSON', '{'],
    ['not a list', '{"id": "x"}'],
  ])('%s reads as no picks', (_, stored) => {
    expect(readPicked(() => stored)).toEqual([])
  })

  test('entries that are not picks are dropped, and only four are kept', () => {
    const stored = JSON.stringify([ride(1), { id: 2 }, 'x', ride(3), ride(4), ride(5), ride(6)])

    expect(readPicked(() => stored).map((p) => p.id)).toEqual(['id-1', 'id-3', 'id-4', 'id-5'])
  })

  test('blocked storage reads as no picks', () => {
    expect(
      readPicked(() => {
        throw new Error('blocked')
      }),
    ).toEqual([])
  })
})

describe('compare address', () => {
  test('ids are comma-separated in order', () => {
    expect(compareUrl(['a', 'b', 'c'])).toBe('/compare?ids=a,b,c')
  })

  test('blanks and repeats are dropped from the address', () => {
    expect(parseIds(' a, ,b,a,c ')).toEqual(['a', 'b', 'c'])
    expect(parseIds(null)).toEqual([])
  })
})
