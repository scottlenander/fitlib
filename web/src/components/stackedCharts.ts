import * as f from '../format'
import type { ZoomControls } from './EChart'

// Layout for charts stacked one per channel (power, heart rate, …) sharing an x axis: each
// chart's title sits above it, with clear space below the chart before, so a title never
// reads as labelling the chart above it.

// Height of one chart's plot.
export const PLOT_HEIGHT = 80
// Plot plus the space above it for its title and the gap after the chart before.
export const ROW_HEIGHT = 135
// How far the zoom bar sits in from each side (its label under it is indented to match).
export const ZOOM_INSET = 70
// Room under the last chart for its axis labels and the zoom bar.
const BOTTOM = 75

// Grids for `count` stacked charts, starting `top` pixels down.
export function stackedGrids(count: number, top: number) {
  return Array.from({ length: count }, (_, i) => ({
    left: 60,
    right: 20,
    top: top + 30 + i * ROW_HEIGHT,
    height: PLOT_HEIGHT,
  }))
}

// The whole chart's height for `count` stacked charts.
export function stackedHeight(count: number, top: number): number {
  return top + 30 + (count - 1) * ROW_HEIGHT + PLOT_HEIGHT + BOTTOM
}

// A stacked chart's y axis, titled above its plot on the left.
export function titledAxis(title: string, gridIndex: number, scale: boolean) {
  return {
    type: 'value',
    gridIndex,
    name: title,
    nameLocation: 'end',
    nameGap: 12,
    nameTextStyle: { align: 'left', fontWeight: 'bold' },
    splitNumber: 2,
    scale,
  }
}

// Zooming on all the stacked charts at once: scrolling or pinching on them, or the bar below,
// whose handles show where they are in the axis's terms.
export function stackedZoom(count: number, over: Over, units: f.Units) {
  const axes = Array.from({ length: count }, (_, i) => i)
  return [
    { type: 'inside', xAxisIndex: axes },
    {
      type: 'slider',
      xAxisIndex: axes,
      bottom: 10,
      height: 20,
      left: ZOOM_INSET,
      right: ZOOM_INSET,
      labelFormatter: (value: number) => xLabel(value, over, units),
    },
  ]
}

// What the shared x axis measures.
export type Over = 'time' | 'distance'

// Where a sample sits on the x axis. Time is in minutes, so the chart's round numbers
// (10, 20, 30) fall on whole minutes at any zoom; distance is in miles or kilometres.
export function xValue(value: number, over: Over, units: f.Units): number {
  return over === 'distance' ? f.distanceValue(value, units) : value / 60
}

// An x-axis value as shown: "1:05:00" for time, "12.5 mi" for distance.
export function xLabel(value: number, over: Over, units: f.Units): string {
  return over === 'distance'
    ? `${value.toFixed(1)} ${f.distanceUnit(units)}`
    : f.duration(value * 60)
}

// The zoom bar's label and reset button.
export const ZOOM: ZoomControls = {
  hint: 'Zoom: drag the ends of the bar under the charts, or scroll on a chart, to look at part of the ride.',
  reset: 'Show whole ride',
  inset: ZOOM_INSET,
}

// One pointer across all the stacked charts, labelled (and the tooltip headed) in the axis's
// terms: "41:09" or "4.4 mi".
export function linkedPointer(over: Over, units: f.Units) {
  return {
    link: [{ xAxisIndex: 'all' }],
    label: { formatter: ({ value }: { value: number }) => xLabel(value, over, units) },
  }
}
