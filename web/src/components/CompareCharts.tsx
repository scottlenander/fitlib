import { useMemo } from 'react'
import type { Comparison, CurvePoint } from '../api/client'
import * as f from '../format'
import { useTheme } from '../theme'
import { useUnits } from '../units'
import { EChart, type ChartOption } from './EChart'
import { seriesColours } from './Swatch'

// The channels overlaid, in the order they're stacked.
const CHANNELS = [
  { field: 'power', label: 'Power', unit: () => 'W', convert: (v: number) => v },
  { field: 'heart_rate', label: 'Heart rate', unit: () => 'bpm', convert: (v: number) => v },
  { field: 'cadence', label: 'Cadence', unit: () => 'rpm', convert: (v: number) => v },
  { field: 'speed', label: 'Speed', unit: f.speedUnit, convert: f.speedValue },
  { field: 'altitude', label: 'Altitude', unit: f.elevationUnit, convert: f.elevationValue },
] as const
type Channel = (typeof CHANNELS)[number]

const ROW_HEIGHT = 120
const LEGEND_HEIGHT = 30

// Overlaid traces, the time gap (lined up by distance) and best efforts of compared rides.
// Each is drawn on a canvas; the figures table on the page holds the numbers.
export function CompareCharts({ comparison }: { comparison: Comparison }) {
  const { units } = useUnits()
  const { theme } = useTheme()
  const names = comparison.rides.map((r) => r.ride.name)
  // Read again when the theme changes, as the tokens do.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const colours = useMemo(() => seriesColours(names.length), [names.length, theme])
  const channels = CHANNELS.filter((c) =>
    comparison.rides.some((r) => r.series[c.field]?.some((v) => v !== null)),
  )
  const x = useMemo(
    () =>
      comparison.align === 'distance'
        ? comparison.x.map((m) => f.distanceValue(m, units))
        : comparison.x,
    [comparison, units],
  )
  const xAxis = {
    type: 'value' as const,
    min: 0,
    max: x[x.length - 1],
    axisLabel: {
      formatter: (v: number) =>
        comparison.align === 'distance'
          ? `${v.toFixed(1)} ${f.distanceUnit(units)}`
          : f.duration(v),
    },
  }

  const traces = useMemo(
    () => tracesOption(comparison, channels, x, xAxis, names, colours, units),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [comparison, x, colours, units],
  )
  const gap = useMemo(
    () =>
      comparison.align === 'distance' ? gapOption(comparison, x, xAxis, names, colours) : null,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [comparison, x, colours],
  )
  const anyPower = comparison.rides.some((r) => r.ride.power_curve.length > 0)
  const curves = useMemo(
    () =>
      curvesOption(
        comparison.rides.map((r) => (anyPower ? r.ride.power_curve : r.ride.hr_curve)),
        anyPower ? 'W' : 'bpm',
        names,
        colours,
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [comparison, anyPower, colours],
  )

  const along = comparison.align === 'distance' ? 'by distance' : 'by time'
  return (
    <>
      <section aria-labelledby="traces-heading">
        <h2 id="traces-heading">Over the ride</h2>
        {channels.length === 0 ? (
          <p>These rides recorded nothing to chart.</p>
        ) : (
          <EChart
            option={traces}
            label={`${channels.map((c) => c.label).join(', ')} of each ride, lined up ${along}`}
            height={channels.length * ROW_HEIGHT + LEGEND_HEIGHT + 60}
            testId="compare-traces"
          />
        )}
      </section>
      {gap && (
        <section aria-labelledby="gap-heading">
          <h2 id="gap-heading">Time gap</h2>
          <p className="hint">
            How far behind (above the line) or ahead (below it) of {names[0]} each ride was at each
            point.
          </p>
          <EChart
            option={gap}
            label={`Each ride's time gap to ${names[0]} along the route`}
            height={260}
            testId="gap-chart"
          />
        </section>
      )}
      <section aria-labelledby="curves-heading">
        <h2 id="curves-heading">Best efforts</h2>
        <EChart
          option={curves}
          label={`Best average ${anyPower ? 'power' : 'heart rate'} by duration for each ride`}
          height={280}
          testId="compare-curves"
        />
      </section>
    </>
  )
}

type XAxis = { type: 'value'; min: number; max: number | undefined; axisLabel: object }

function tracesOption(
  comparison: Comparison,
  channels: Channel[],
  x: number[],
  xAxis: XAxis,
  names: string[],
  colours: string[],
  units: f.Units,
): ChartOption {
  return {
    animation: false,
    color: colours,
    legend: { top: 0, data: names },
    grid: channels.map((_, i) => ({
      left: 60,
      right: 20,
      top: LEGEND_HEIGHT + 20 + i * ROW_HEIGHT,
      height: ROW_HEIGHT - 30,
    })),
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: unknown) => (typeof v === 'number' ? v.toFixed(0) : ''),
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    dataZoom: [
      { type: 'inside', xAxisIndex: channels.map((_, i) => i) },
      { type: 'slider', xAxisIndex: channels.map((_, i) => i), bottom: 10, height: 20 },
    ],
    xAxis: channels.map((_, i) => ({
      ...xAxis,
      gridIndex: i,
      axisLabel: { ...xAxis.axisLabel, show: i === channels.length - 1 },
    })),
    yAxis: channels.map((c, i) => ({
      type: 'value',
      gridIndex: i,
      name: `${c.label} (${c.unit(units)})`,
      nameTextStyle: { align: 'left' },
      splitNumber: 2,
      scale: c.field !== 'power',
    })),
    series: channels.flatMap((c, i) =>
      comparison.rides.map((ride, r) => ({
        name: names[r],
        type: 'line',
        xAxisIndex: i,
        yAxisIndex: i,
        showSymbol: false,
        lineStyle: { width: 2 },
        color: colours[r],
        data: (ride.series[c.field] ?? []).map((v, k) => [
          x[k],
          typeof v === 'number' ? Number(c.convert(v, units).toFixed(1)) : null,
        ]),
      })),
    ),
  }
}

// Signed time: "+1:05" behind, "-0:20" ahead.
const signed = (seconds: number) =>
  `${seconds > 0 ? '+' : seconds < 0 ? '-' : ''}${f.duration(Math.abs(seconds))}`

function gapOption(
  comparison: Comparison,
  x: number[],
  xAxis: XAxis,
  names: string[],
  colours: string[],
): ChartOption {
  return {
    animation: false,
    color: colours,
    legend: { top: 0, data: names },
    grid: { left: 60, right: 20, top: 40, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: unknown) => (typeof v === 'number' ? signed(v) : ''),
    },
    xAxis,
    yAxis: {
      type: 'value',
      name: 'Gap',
      axisLabel: { formatter: (v: number) => signed(v) },
    },
    series: comparison.rides.map((ride, r) => ({
      name: names[r],
      type: 'line',
      showSymbol: false,
      lineStyle: { width: 2 },
      color: colours[r],
      data: (ride.gap ?? []).map((v, k) => [x[k], v]),
    })),
  }
}

function curvesOption(
  curves: CurvePoint[][],
  unit: string,
  names: string[],
  colours: string[],
): ChartOption {
  const durations = [...new Set(curves.flat().map((p) => p.duration_s))].sort((a, b) => a - b)
  return {
    animation: false,
    color: colours,
    legend: { top: 0, data: names },
    grid: { left: 60, right: 20, top: 40, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: unknown) => (typeof v === 'number' ? `${v.toFixed(0)} ${unit}` : ''),
    },
    xAxis: { type: 'category', data: durations.map(f.shortDuration), boundaryGap: false },
    yAxis: { type: 'value', name: unit, scale: true },
    series: curves.map((curve, r) => ({
      name: names[r],
      type: 'line',
      lineStyle: { width: 2 },
      symbolSize: 8,
      color: colours[r],
      data: durations.map((d) => curve.find((p) => p.duration_s === d)?.value ?? null),
    })),
  }
}
