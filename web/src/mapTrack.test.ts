import { describe, expect, it } from 'vitest'
import type { MapPoint } from './api/client'
import { positionAt, stretch } from './mapTrack'

// Due east along the equator: 0.001° every 10 s.
const POINTS: MapPoint[] = [0, 10, 20, 30].map((t) => ({
  t,
  lat: 0,
  lon: t / 10000,
  distance_m: t * 11,
}))

describe('positionAt', () => {
  it('finds a point recorded at that moment', () => {
    expect(positionAt(POINTS, 20)).toEqual([0, 0.002])
  })

  it('places a moment between two points in proportion', () => {
    const [lat, lon] = positionAt(POINTS, 15) ?? [NaN, NaN]
    expect(lat).toBe(0)
    expect(lon).toBeCloseTo(0.0015, 9)
  })

  it('has no position before the start, after the end, or without points', () => {
    expect(positionAt(POINTS, -1)).toBeNull()
    expect(positionAt(POINTS, 31)).toBeNull()
    expect(positionAt([], 0)).toBeNull()
  })
})

describe('stretch', () => {
  it('runs from the first moment to the second, with the points between', () => {
    const line = stretch(POINTS, 5, 25)
    expect(line.map(([, lon]) => Number(lon.toFixed(4)))).toEqual([0.0005, 0.001, 0.002, 0.0025])
  })

  it('is empty when both moments are outside the ride', () => {
    expect(stretch(POINTS, 40, 50)).toEqual([])
  })
})
