import { useEffect, useMemo, useState } from 'react'
import { useStreams, type Streams } from '../api/client'
import * as f from '../shared/format'
import { useUnits } from '../shared/units'
import { EChart, type ChartOption } from '../charts/EChart'
import {
  ZOOM,
  linkedPointer,
  stackedGrids,
  stackedHeight,
  stackedZoom,
  titledAxis,
  xLabel,
  xValue,
  type Over,
} from '../charts/stackedCharts'

// The channels a ride can have, in the order they're stacked.
const CHANNELS = [
  { field: 'power', label: 'Power', unit: () => 'W', convert: (v: number) => v },
  { field: 'heart_rate', label: 'Heart rate', unit: () => 'bpm', convert: (v: number) => v },
  { field: 'cadence', label: 'Cadence', unit: () => 'rpm', convert: (v: number) => v },
  { field: 'speed', label: 'Speed', unit: f.speedUnit, convert: f.speedValue },
  { field: 'altitude', label: 'Altitude', unit: f.elevationUnit, convert: f.elevationValue },
] as const
type Channel = (typeof CHANNELS)[number]

const POINTS = 1500 // about one point per pixel on a wide screen

type Props = {
  rideId: string
  elapsedS: number
  hasPower: boolean
  hasHr: boolean
  hasDistance: boolean
  // The moment under the pointer, and the stretch zoomed to, in seconds from the start (for
  // the map); null when there's none.
  onMoment?: (t: number | null) => void
  onSpan?: (span: [number, number] | null) => void
}

// Seconds from the start at an x value: the chart's x is time or distance, in display units.
export function secondsAt(xs: number[], ts: number[], x: number): number | null {
  if (!xs.length) return null
  let lo = 0
  let hi = xs.length - 1
  if (x <= (xs[0] ?? 0)) return ts[0] ?? null
  if (x >= (xs[hi] ?? 0)) return ts[hi] ?? null
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if ((xs[mid] ?? 0) <= x) lo = mid
    else hi = mid
  }
  const x0 = xs[lo] ?? 0
  const x1 = xs[hi] ?? 0
  const t0 = ts[lo] ?? 0
  const t1 = ts[hi] ?? 0
  return x1 === x0 ? t0 : t0 + ((t1 - t0) * (x - x0)) / (x1 - x0)
}

// One line per recorded channel, stacked, sharing a time or distance axis that zooms
// together.
export function TraceChart(props: Props) {
  const { rideId, elapsedS, hasPower, hasHr, hasDistance, onMoment, onSpan } = props
  const { units } = useUnits()
  const [chosen, setOver] = useState<Over>('time')
  const over = hasDistance ? chosen : 'time'
  const step = Math.max(1, Math.ceil(elapsedS / POINTS))
  const fields = [
    ...CHANNELS.map((c) => c.field).filter(
      (field) => (field !== 'power' || hasPower) && (field !== 'heart_rate' || hasHr),
    ),
    ...(hasDistance ? ['distance'] : []),
  ]
  const streams = useStreams(rideId, fields, step, true)

  const shown = useMemo(
    () =>
      streams.data
        ? CHANNELS.filter((c) => streams.data.columns[c.field]?.some((v) => v !== null))
        : [],
    [streams.data],
  )
  const option = useMemo(
    () => (streams.data ? chartOption(streams.data, shown, over, units) : null),
    [streams.data, shown, over, units],
  )
  // The chart's x values with their seconds, to turn the pointer and zoom into moments.
  const axis = useMemo(() => {
    const xs: number[] = []
    const ts: number[] = []
    if (!streams.data) return { xs, ts }
    const raw = over === 'distance' ? (streams.data.columns.distance ?? []) : streams.data.t
    raw.forEach((v, i) => {
      const t = streams.data.t[i]
      if (typeof v === 'number' && typeof t === 'number') {
        xs.push(xValue(v, over, units))
        ts.push(t)
      }
    })
    return { xs, ts }
  }, [streams.data, over, units])
  // A new drawing starts unzoomed.
  useEffect(() => onSpan?.(null), [option, onSpan])

  return (
    <>
      <div role="radiogroup" aria-label="Show over" className="radios">
        <span aria-hidden="true">Show over</span>
        {(['time', 'distance'] as const).map((value) => (
          <label key={value}>
            <input
              type="radio"
              name="trace-over"
              value={value}
              checked={over === value}
              disabled={value === 'distance' && !hasDistance}
              onChange={() => setOver(value)}
            />
            {value === 'time' ? 'Time' : 'Distance'}
          </label>
        ))}
        {!hasDistance && <span className="hint">(this ride recorded no distance)</span>}
      </div>
      {streams.isError && <p role="alert">Couldn't load the ride's samples.</p>}
      {!streams.isError && !option && <p>Loading samples…</p>}
      {option && (
        <EChart
          option={option}
          label={`${shown.map((c) => c.label).join(', ')} over the ride, by ${over}`}
          height={stackedHeight(shown.length, 0)}
          testId="trace-chart"
          zoom={ZOOM}
          onPointer={(x) => onMoment?.(x === null ? null : secondsAt(axis.xs, axis.ts, x))}
          onRange={(range) => {
            const from = range && secondsAt(axis.xs, axis.ts, range[0])
            const to = range && secondsAt(axis.xs, axis.ts, range[1])
            onSpan?.(
              from !== null && to !== null && from !== undefined && to !== undefined
                ? [from, to]
                : null,
            )
          }}
        />
      )}
    </>
  )
}

function chartOption(
  streams: Streams,
  channels: Channel[],
  over: Over,
  units: f.Units,
): ChartOption {
  const distance = streams.columns.distance ?? []
  const raw: (number | null | boolean)[] = over === 'distance' ? distance : streams.t
  const x = raw.map((v) => (typeof v === 'number' ? xValue(v, over, units) : null))
  const last = x.reduce<number>((top, v) => (v !== null && v > top ? v : top), 0)
  return {
    animation: false,
    grid: stackedGrids(channels.length, 0),
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: unknown) => (typeof v === 'number' ? v.toFixed(0) : ''),
    },
    axisPointer: linkedPointer(over, units),
    dataZoom: stackedZoom(channels.length, over, units),
    xAxis: channels.map((_, i) => ({
      type: 'value',
      gridIndex: i,
      min: 0,
      max: last,
      axisLabel: {
        show: i === channels.length - 1,
        formatter: (v: number) => xLabel(v, over, units),
      },
    })),
    yAxis: channels.map((c, i) =>
      titledAxis(`${c.label} (${c.unit(units)})`, i, c.field !== 'power'),
    ),
    series: channels.map((c, i) => ({
      name: c.label,
      type: 'line',
      xAxisIndex: i,
      yAxisIndex: i,
      showSymbol: false,
      lineStyle: { width: 1 },
      // Seconds without a distance (pauses) have no place on a distance axis.
      data: (streams.columns[c.field] ?? []).flatMap((v, k) =>
        x[k] === null || x[k] === undefined
          ? []
          : [[x[k], typeof v === 'number' ? Number(c.convert(v, units).toFixed(1)) : null]],
      ),
    })),
  }
}
