// The trends page's and route progress's charts. Each is drawn on a canvas; the tables next to
// them hold the same numbers. Loaded only when needed, with ECharts.
import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import type {
  CurveBest,
  EfficiencyPoint,
  FitnessDay,
  Ftp,
  RideItem,
  VolumeBucket,
} from '../api/client'
import * as f from '../format'
import {
  rollingAverage,
  volumeUnit,
  volumeValue,
  type Metric,
  type Period,
} from '../pages/trendsQuery'
import { useTheme } from '../theme'
import { useUnits } from '../units'
import { EChart, type ChartOption } from './EChart'
import { PROGRESS_METRICS, progressValue, type ProgressMetric } from './progressMetrics'
import { stackedGrids, stackedHeight, titledAxis } from './stackedCharts'
import { seriesColours } from './Swatch'

const LEGEND = 30
const DAY_MS = 86_400_000
const GRID = { left: 60, right: 20, top: 50, bottom: 40 }
const LINE = { type: 'line', showSymbol: false, lineStyle: { width: 2 } } as const
const round = (digits: number) => (v: unknown) => (typeof v === 'number' ? v.toFixed(digits) : '')

// The categorical colours, read again when the theme changes (the tokens do).
function useColours(): string[] {
  const { theme } = useTheme()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => seriesColours(4), [theme])
}

// A date axis from the first to the last day, labelled "18 Aug".
function dayAxis(since: string, until: string, gridIndex = 0, labels = true) {
  return {
    type: 'time',
    gridIndex,
    min: since,
    max: until,
    axisLabel: { show: labels, formatter: '{dd} {MMM}', hideOverlap: true },
  }
}

// Tooltip heading for a date axis: "Mon 18 Aug 2025".
function dayTooltip(digits: number, unit = '') {
  return {
    trigger: 'axis',
    axisPointer: { label: { formatter: ({ value }: { value: number }) => f.day(isoDay(value)) } },
    valueFormatter: (v: unknown) => (typeof v === 'number' ? `${v.toFixed(digits)}${unit}` : '–'),
  }
}

// An ECharts time value (milliseconds, local time) back to YYYY-MM-DD.
function isoDay(ms: number): string {
  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

type Range = { since: string; until: string }

// Fitness and fatigue as lines over daily TSS bars, with form below.
export function FitnessChart({ days, range }: { days: FitnessDay[]; range: Range }) {
  const colours = useColours()
  const option = useMemo<ChartOption>(
    () => ({
      animation: false,
      legend: { top: 0, data: ['Fitness', 'Fatigue', 'Daily TSS', 'Form'] },
      grid: stackedGrids(2, LEGEND),
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      tooltip: dayTooltip(0),
      xAxis: [dayAxis(range.since, range.until, 0, false), dayAxis(range.since, range.until, 1)],
      yAxis: [titledAxis('Load (TSS a day)', 0, false), titledAxis('Form', 1, false)],
      series: [
        {
          name: 'Daily TSS',
          type: 'bar',
          barMaxWidth: 8,
          color: colours[2],
          itemStyle: { borderRadius: [2, 2, 0, 0] },
          data: days.map((d) => [d.day, d.tss]),
        },
        { ...LINE, name: 'Fitness', color: colours[0], data: days.map((d) => [d.day, d.fitness]) },
        { ...LINE, name: 'Fatigue', color: colours[1], data: days.map((d) => [d.day, d.fatigue]) },
        {
          ...LINE,
          name: 'Form',
          xAxisIndex: 1,
          yAxisIndex: 1,
          color: colours[3],
          areaStyle: { opacity: 0.15 },
          data: days.map((d) => [d.day, d.form]),
        },
      ],
    }),
    [days, range, colours],
  )
  return (
    <EChart
      option={option}
      label="Fitness, fatigue and daily TSS, with form below, for each day of the range"
      height={stackedHeight(2, LEGEND) - 30}
      testId="fitness-chart"
    />
  )
}

type VolumeProps = { buckets: VolumeBucket[]; metric: Metric; period: Period }

// One bar per week or month.
export function VolumeChart({ buckets, metric, period }: VolumeProps) {
  const { units } = useUnits()
  const colours = useColours()
  const unit = volumeUnit(metric, units)
  const option = useMemo<ChartOption>(
    () => ({
      animation: false,
      grid: { ...GRID, top: 30 },
      tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => `${String(v)} ${unit}` },
      xAxis: {
        type: 'category',
        data: buckets.map((b) => (period === 'week' ? f.shortDay(b.start) : f.month(b.start))),
        axisLabel: { hideOverlap: true },
      },
      yAxis: { type: 'value', name: unit },
      series: [
        {
          type: 'bar',
          name: unit,
          barMaxWidth: 28,
          color: colours[0],
          itemStyle: { borderRadius: [4, 4, 0, 0] },
          data: buckets.map((b) => volumeValue(b, metric, units)),
        },
      ],
    }),
    [buckets, metric, period, units, unit, colours],
  )
  return (
    <EChart
      option={option}
      label={`Volume by ${period}: ${unit === 'h' ? 'hours' : unit}`}
      height={260}
      testId="volume-chart"
    />
  )
}

// Set FTP as steps, and the estimate, at the end of each week or month.
export function FtpChart({ ftp }: { ftp: Ftp }) {
  const colours = useColours()
  const option = useMemo<ChartOption>(
    () => ({
      animation: false,
      legend: { top: 0, data: ['Set FTP', 'Estimated FTP'] },
      grid: GRID,
      tooltip: dayTooltip(0, ' W'),
      xAxis: dayAxis(ftp.points[0]?.day ?? ftp.since, ftp.until),
      yAxis: { type: 'value', name: 'W', scale: true },
      series: [
        {
          ...LINE,
          name: 'Set FTP',
          step: 'end',
          color: colours[0],
          data: ftp.points.map((p) => [p.day, p.ftp]),
        },
        {
          ...LINE,
          name: 'Estimated FTP',
          showSymbol: true,
          symbolSize: 8,
          color: colours[1],
          data: ftp.points.map((p) => [p.day, p.estimated]),
        },
      ],
    }),
    [ftp, colours],
  )
  return (
    <EChart
      option={option}
      label={`Set and estimated FTP at the end of each ${ftp.period}`}
      height={260}
      testId="ftp-chart"
    />
  )
}

type EfficiencyProps = { points: EfficiencyPoint[]; range: Range }

// A dot per ride (outdoor circles, indoor triangles), and the 28-day average; a dot opens its
// ride.
export function EfficiencyChart({ points, range }: EfficiencyProps) {
  const colours = useColours()
  const navigate = useNavigate()
  const option = useMemo<ChartOption>(() => {
    const average = rollingAverage(points, (p) => p.efficiency)
    const dots = (indoor: boolean) =>
      points
        .filter((p) => p.indoor === indoor)
        .map((p) => ({ value: [p.day, Number(p.efficiency.toFixed(2))], id: p.ride_id }))
    return {
      animation: false,
      legend: { top: 0, data: ['Outdoor', 'Indoor', '28-day average'] },
      grid: GRID,
      tooltip: dayTooltip(2, ' W/bpm'),
      xAxis: dayAxis(range.since, range.until),
      yAxis: { type: 'value', name: 'W/bpm', scale: true },
      series: [
        { name: 'Outdoor', type: 'scatter', symbolSize: 10, color: colours[0], data: dots(false) },
        {
          name: 'Indoor',
          type: 'scatter',
          symbol: 'triangle',
          symbolSize: 11,
          color: colours[1],
          data: dots(true),
        },
        {
          ...LINE,
          name: '28-day average',
          color: colours[2],
          data: points.map((p, i) => [p.day, Number(average[i]!.toFixed(2))]),
        },
      ],
    }
  }, [points, range, colours])
  return (
    <EChart
      option={option}
      label="Efficiency of each ride (NP per bpm) and its 28-day average"
      height={280}
      testId="efficiency-chart"
      onItemClick={(data) => {
        const id = (data as { id?: string } | undefined)?.id
        if (id) void navigate(`/rides/${id}`)
      }}
    />
  )
}

type CurveProps = { curves: CurveBest[][]; names: string[]; unit: string }

// The range's best efforts against the comparison's, by duration.
export function BestCurveChart({ curves, names, unit }: CurveProps) {
  const colours = useColours()
  const option = useMemo<ChartOption>(() => {
    const durations = [...new Set(curves.flat().map((p) => p.duration_s))].sort((a, b) => a - b)
    return {
      animation: false,
      legend: { top: 0, data: names },
      grid: GRID,
      tooltip: { trigger: 'axis', valueFormatter: round(0) },
      xAxis: { type: 'category', data: durations.map(f.shortDuration), boundaryGap: false },
      yAxis: { type: 'value', name: unit, scale: true },
      series: curves.map((curve, i) => ({
        type: 'line',
        name: names[i],
        lineStyle: { width: 2 },
        symbolSize: 8,
        color: colours[i],
        // The range's own line on top, so it shows where the two are the same.
        z: curves.length - i + 2,
        data: durations.map((d) => curve.find((p) => p.duration_s === d)?.value ?? null),
      })),
    }
  }, [curves, names, unit, colours])
  return (
    <EChart
      option={option}
      label={`Best ${unit === 'W' ? 'power' : 'heart rate'} by duration: ${names.join(' against ')}`}
      height={280}
      testId="best-curve-chart"
    />
  )
}

type ProgressProps = { rides: RideItem[]; rideId: string; metric: ProgressMetric }

// The route's rides over time, this one picked out larger and in another colour.
export function ProgressChart({ rides, rideId, metric }: ProgressProps) {
  const { units } = useUnits()
  const colours = useColours()
  const unit = { speed: f.speedUnit(units), power: 'W', hr: 'bpm', time: 'min' }[metric]
  const option = useMemo<ChartOption>(
    () => ({
      animation: false,
      legend: { top: 0, data: ['Rides on this route', 'This ride'] },
      grid: GRID,
      tooltip: dayTooltip(1, ` ${unit}`),
      // Two days' room at each end, so the first and last rides' markers aren't cut in half.
      xAxis: {
        type: 'time',
        min: ({ min }: { min: number }) => min - 2 * DAY_MS,
        max: ({ max }: { max: number }) => max + 2 * DAY_MS,
        axisLabel: { formatter: '{dd} {MMM} {yy}', hideOverlap: true },
      },
      yAxis: { type: 'value', name: unit, scale: true },
      series: [
        {
          type: 'line',
          name: 'Rides on this route',
          lineStyle: { width: 2 },
          symbolSize: 8,
          color: colours[0],
          connectNulls: true,
          data: rides.map((r) => [f.date(r.start, r.local_start), progressValue(r, metric, units)]),
        },
        {
          type: 'scatter',
          name: 'This ride',
          symbol: 'diamond',
          symbolSize: 16,
          z: 3,
          color: colours[1],
          data: rides
            .filter((r) => r.id === rideId)
            .map((r) => [f.date(r.start, r.local_start), progressValue(r, metric, units)]),
        },
      ],
    }),
    [rides, rideId, metric, unit, units, colours],
  )
  return (
    <EChart
      option={option}
      label={`${PROGRESS_METRICS.find((m) => m.id === metric)!.label} of each ride on this route, by date`}
      height={240}
      testId="progress-chart"
    />
  )
}
