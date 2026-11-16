// Formatting, in both unit systems. Expected values match fitlib's display.py tests.
import { describe, expect, test } from 'vitest'
import * as f from './format'

describe('durations', () => {
  test.each([
    [0, '0:00'],
    [65, '1:05'],
    [2525, '42:05'],
    [3600, '1:00:00'],
    [3725, '1:02:05'],
    [null, f.DASH],
  ])('%s s is %s', (seconds, text) => {
    expect(f.duration(seconds)).toBe(text)
  })

  test.each([
    [5, '5 s'],
    [60, '1 min'],
    [1200, '20 min'],
    [3600, '1 h'],
    [5400, '1 h 30 min'],
  ])('short duration of %s s is %s', (seconds, text) => {
    expect(f.shortDuration(seconds)).toBe(text)
  })
})

describe('units', () => {
  test.each([
    ['imperial', '19.9 mi', '19.9 mph', '427 ft', '165.0 lb'],
    ['metric', '32.0 km', '32.0 km/h', '130 m', '74.8 kg'],
  ] as const)('%s', (units, dist, spd, height, mass) => {
    expect(f.distance(32_000, units)).toBe(dist)
    expect(f.speed(32 / 3.6, units)).toBe(spd)
    expect(f.elevation(130, units)).toBe(height)
    expect(f.weight(74.84, units)).toBe(mass)
  })

  test('missing values are a dash in either system', () => {
    for (const units of ['imperial', 'metric'] as const) {
      expect([f.distance(null, units), f.speed(null, units), f.elevation(null, units)]).toEqual([
        f.DASH,
        f.DASH,
        f.DASH,
      ])
    }
  })

  test('chart values convert speed and altitude', () => {
    expect(f.speedValue(10, 'metric')).toBeCloseTo(36)
    expect(f.speedValue(10, 'imperial')).toBeCloseTo(22.369, 3)
    expect(f.elevationValue(100, 'imperial')).toBeCloseTo(328.084, 3)
    expect([f.speedUnit('imperial'), f.elevationUnit('metric')]).toEqual(['mph', 'm'])
  })
})

describe('figures', () => {
  test('power, heart rate, cadence, work and ratios', () => {
    expect(f.watts(187.4)).toBe('187 W')
    expect(f.bpm(137)).toBe('137 bpm')
    expect(f.rpm(87.2)).toBe('87 rpm')
    expect(f.kilojoules(720.4)).toBe('720 kJ')
    expect(f.ratio(0.8)).toBe('0.80')
    expect(f.tss(64.2)).toBe('64')
    expect(f.wattsPerKg(2.666)).toBe('2.67 W/kg')
    expect([f.signedPercent(3.24), f.signedPercent(-0.4)]).toEqual(['+3.2 %', '-0.4 %'])
    expect(f.watts(null)).toBe(f.DASH)
  })
})

describe('times', () => {
  test('local start is shown as recorded, with no zone conversion', () => {
    expect(f.startTime('2025-08-05T17:00:00Z', '2025-08-05T19:00:00')).toBe(
      'Tue 05 Aug 2025, 19:00',
    )
    expect(f.date('2025-08-05T23:30:00Z', '2025-08-06T01:30:00')).toBe('2025-08-06')
  })

  test('without a local time, UTC is shown and labelled', () => {
    expect(f.startTime('2025-08-02T06:30:00Z', null)).toBe('Sat 02 Aug 2025, 06:30 UTC')
    expect(f.date('2025-08-02T06:30:00Z')).toBe('2025-08-02')
  })
})
