// The stacked charts' layout and x axis.
import { describe, expect, test } from 'vitest'
import { PLOT_HEIGHT, stackedGrids, stackedHeight, xLabel, xValue } from './stackedCharts'

describe('stacked layout', () => {
  test('each title has clear space below the chart above it', () => {
    const [first, second] = stackedGrids(2, 0)

    const gap = second!.top - (first!.top + PLOT_HEIGHT)

    expect(gap).toBeGreaterThanOrEqual(50)
  })

  test('the whole chart leaves room under the last plot for its labels and zoom bar', () => {
    const grids = stackedGrids(3, 30)
    const last = grids[2]!

    expect(stackedHeight(3, 30) - (last.top + PLOT_HEIGHT)).toBeGreaterThanOrEqual(70)
  })
})

describe('x axis', () => {
  test('time is plotted in minutes and shown as a clock', () => {
    expect(xValue(2469, 'time', 'imperial')).toBeCloseTo(41.15)
    expect(xLabel(41.15, 'time', 'imperial')).toBe('41:09')
    expect(xLabel(65, 'time', 'metric')).toBe('1:05:00')
  })

  test('distance is plotted and shown in the chosen units', () => {
    expect(xValue(16093.44, 'distance', 'imperial')).toBeCloseTo(10)
    expect(xLabel(10, 'distance', 'imperial')).toBe('10.0 mi')
    expect(xValue(12500, 'distance', 'metric')).toBe(12.5)
    expect(xLabel(12.5, 'distance', 'metric')).toBe('12.5 km')
  })
})
