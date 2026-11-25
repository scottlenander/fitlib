// The trends page's URL state and the date sums behind its ranges.
import { describe, expect, test } from 'vitest'
import {
  addDays,
  againstRange,
  daysBetween,
  fromParams,
  localToday,
  periodLabel,
  resolveRange,
  rollingAverage,
  toParams,
  volumeUnit,
  volumeValue,
} from './trendsQuery'

const parse = (search: string) => fromParams(new URLSearchParams(search))
const TODAY = '2026-03-18'
const FIRST_RIDE = '2025-08-02'

describe('reading and writing the URL', () => {
  test('an empty URL is 3 months by week, time, power against the past year', () => {
    expect(parse('')).toEqual({
      range: '3m',
      since: '',
      until: '',
      period: 'week',
      metric: 'time',
      curve: 'power',
      against: 'year',
    })
    expect(toParams(parse('')).toString()).toBe('')
  })

  test('unknown values fall back to the defaults', () => {
    const state = parse('range=2y&period=day&metric=watts&curve=cadence&against=ever')

    expect(state).toMatchObject({ range: '3m', period: 'week', metric: 'time', curve: 'power' })
    expect(state.against).toBe('year')
  })

  test('dates make a custom range; bad dates are ignored', () => {
    expect(parse('range=1y&since=2025-08-18&until=2025-08-31')).toMatchObject({
      range: 'custom',
      since: '2025-08-18',
      until: '2025-08-31',
    })
    expect(parse('since=2025-13-45').range).toBe('3m')
  })

  test('a full state round-trips', () => {
    const preset = 'range=1y&period=month&metric=tss&curve=hr&against=previous'
    const custom = 'since=2025-08-18&until=2025-08-31&against=all'

    expect(toParams(parse(preset)).toString()).toBe(preset)
    expect(toParams(parse(custom)).toString()).toBe(custom)
  })
})

describe('dates', () => {
  test('adding days crosses months and years', () => {
    expect(addDays('2025-12-30', 3)).toBe('2026-01-02')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(daysBetween('2025-08-18', '2025-08-31')).toBe(13)
  })

  test("today is this computer's date, not UTC's", () => {
    expect(localToday(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05')
  })

  test.each([
    ['6w', '2026-02-05'],
    ['3m', '2025-12-18'],
    ['6m', '2025-09-17'],
    ['1y', '2025-03-19'],
    ['all', FIRST_RIDE],
  ])('preset %s ends today and starts on %s', (range, since) => {
    expect(resolveRange(parse(`range=${range}`), TODAY, FIRST_RIDE)).toEqual({
      since,
      until: TODAY,
    })
  })

  test('"All" in an empty library is just today; open custom ranges are filled in', () => {
    expect(resolveRange(parse('range=all'), TODAY, null)).toEqual({ since: TODAY, until: TODAY })
    expect(resolveRange(parse('since=2025-08-01'), TODAY, null)).toEqual({
      since: '2025-08-01',
      until: TODAY,
    })
    expect(resolveRange(parse('until=2025-08-31'), TODAY, null)).toEqual({
      since: '2025-06-03',
      until: '2025-08-31',
    })
  })

  test('best efforts are compared with the past year, all time, or the period before', () => {
    const range = { since: '2025-08-18', until: '2025-08-31' }

    expect(againstRange('year', range, FIRST_RIDE)).toEqual({
      since: '2024-09-01',
      until: '2025-08-31',
    })
    expect(againstRange('all', range, FIRST_RIDE)).toEqual({
      since: FIRST_RIDE,
      until: '2025-08-31',
    })
    expect(againstRange('previous', range, FIRST_RIDE)).toEqual({
      since: '2025-08-04',
      until: '2025-08-17',
    })
  })
})

describe('rolling average', () => {
  test('each point averages the points in the 28 days up to it', () => {
    const points = [
      { day: '2025-08-01', v: 1 },
      { day: '2025-08-10', v: 2 },
      { day: '2025-08-28', v: 3 }, // 27 days after the first: still in its window
      { day: '2025-08-29', v: 6 }, // 28 days after: the first drops out
    ]

    expect(rollingAverage(points, (p) => p.v)).toEqual([1, 1.5, 2, 11 / 3])
  })
})

describe('volume figures', () => {
  const week = {
    start: '2025-08-18',
    rides: 3,
    moving_s: 4500,
    distance_m: 40_555,
    ascent_m: 164,
    kj: 832,
    tss: 91.6,
    rides_without_tss: 0,
  }

  test.each([
    ['time', 'imperial', 1.25, 'h'],
    ['distance', 'imperial', 25.2, 'mi'],
    ['distance', 'metric', 40.6, 'km'],
    ['ascent', 'imperial', 538, 'ft'],
    ['tss', 'imperial', 92, 'TSS'],
    ['rides', 'metric', 3, 'Rides'],
  ] as const)('%s in %s: %s %s', (metric, units, value, unit) => {
    expect(volumeValue(week, metric, units)).toBe(value)
    expect(volumeUnit(metric, units)).toBe(unit)
  })

  test('weeks and months are labelled', () => {
    expect(periodLabel('2025-08-18', 'week')).toBe('Week of 18 Aug 2025')
    expect(periodLabel('2025-08-01', 'month')).toBe('Aug 2025')
  })
})
