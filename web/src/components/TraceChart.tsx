import { useMemo } from 'react'
import { useStreams, type Streams } from '../api/client'
import * as f from '../format'
import { useUnits } from '../units'
import { EChart, type ChartOption } from './EChart'

// The channels a ride can have, in the order they're stacked.
const CHANNELS = [
  { field: 'power', label: 'Power', unit: () => 'W', convert: (v: number) => v },
  { field: 'heart_rate', label: 'Heart rate', unit: () => 'bpm', convert: (v: number) => v },
  { field: 'cadence', label: 'Cadence', unit: () => 'rpm', convert: (v: number) => v },
  { field: 'speed', label: 'Speed', unit: f.speedUnit, convert: f.speedValue },
  { field: 'altitude', label: 'Altitude', unit: f.elevationUnit, convert: f.elevationValue },
] as const

const POINTS = 1500 // about one point per pixel on a wide screen
const ROW_HEIGHT = 110

type Props = { rideId: string; elapsedS: number; hasPower: boolean; hasHr: boolean }

// One line per recorded channel, stacked, sharing a time axis that can be zoomed together.
export function TraceChart({ rideId, elapsedS, hasPower, hasHr }: Props) {
  const { units } = useUnits()
  const step = Math.max(1, Math.ceil(elapsedS / POINTS))
  const fields = CHANNELS.map((c) => c.field).filter(
    (field) => (field !== 'power' || hasPower) && (field !== 'heart_rate' || hasHr),
  )
  const streams = useStreams(rideId, fields, step, true)

  const shown = useMemo(
    () =>
      streams.data
        ? CHANNELS.filter((c) => streams.data.columns[c.field]?.some((v) => v !== null))
        : [],
    [streams.data],
  )
  const option = useMemo(
    () => (streams.data ? chartOption(streams.data, shown, units) : null),
    [streams.data, shown, units],
  )

  if (streams.isError) return <p role="alert">Couldn't load the ride's samples.</p>
  if (!option) return <p>Loading samples…</p>
  const label = `${shown.map((c) => c.label).join(', ')} over the ride`
  return (
    <EChart
      option={option}
      label={label}
      height={shown.length * ROW_HEIGHT + 70}
      testId="trace-chart"
    />
  )
}

function chartOption(
  streams: Streams,
  channels: (typeof CHANNELS)[number][],
  units: f.Units,
): ChartOption {
  const time = streams.t
  const grids = channels.map((_, i) => ({
    left: 60,
    right: 20,
    top: 20 + i * ROW_HEIGHT,
    height: ROW_HEIGHT - 30,
  }))
  return {
    animation: false,
    grid: grids,
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
      type: 'category',
      gridIndex: i,
      data: time.map((t) => f.duration(t)),
      axisLabel: { show: i === channels.length - 1 },
      boundaryGap: false,
    })),
    yAxis: channels.map((c, i) => ({
      type: 'value',
      gridIndex: i,
      name: `${c.label} (${c.unit(units)})`,
      nameTextStyle: { align: 'left' },
      splitNumber: 2,
      scale: c.field !== 'power',
    })),
    series: channels.map((c, i) => ({
      name: c.label,
      type: 'line',
      xAxisIndex: i,
      yAxisIndex: i,
      showSymbol: false,
      lineStyle: { width: 1 },
      data: (streams.columns[c.field] ?? []).map((v) =>
        typeof v === 'number' ? Number(c.convert(v, units).toFixed(1)) : null,
      ),
    })),
  }
}
