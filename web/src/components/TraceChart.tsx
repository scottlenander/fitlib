import { useMemo, useState } from 'react'
import { useStreams, type Streams } from '../api/client'
import * as f from '../format'
import { useUnits } from '../units'
import { EChart, type ChartOption } from './EChart'
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
} from './stackedCharts'

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
}

// One line per recorded channel, stacked, sharing a time or distance axis that zooms
// together.
export function TraceChart({ rideId, elapsedS, hasPower, hasHr, hasDistance }: Props) {
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
