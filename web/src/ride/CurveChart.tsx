import { useMemo } from 'react'
import type { CurvePoint } from '../api/rides'
import * as f from '../shared/format'
import { EChart, type ChartOption } from '../charts/EChart'

// Durations shown in the best-efforts table, as in `fitlib show`.
const SHOWN = [5, 60, 300, 1200, 3600]

type Props = { power: CurvePoint[]; hr: CurvePoint[] }

// Best average power and heart rate over each duration: a chart and a table of key ones.
export function BestEfforts({ power, hr }: Props) {
  const option = useMemo(() => curveOption(power, hr), [power, hr])
  const at = (curve: CurvePoint[], seconds: number) =>
    curve.find((p) => p.duration_s === seconds)?.value
  const rows = SHOWN.filter((s) => at(power, s) !== undefined || at(hr, s) !== undefined)
  return (
    <>
      <EChart
        option={option}
        label="Best average power and heart rate by duration"
        height={260}
        testId="curve-chart"
      />
      <table data-testid="efforts-table">
        <caption className="visually-hidden">Best efforts</caption>
        <thead>
          <tr>
            <th scope="col">Best</th>
            {power.length > 0 && (
              <th scope="col" className="num">
                Power
              </th>
            )}
            <th scope="col" className="num">
              Heart rate
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((seconds) => (
            <tr key={seconds}>
              <th scope="row">{f.shortDuration(seconds)}</th>
              {power.length > 0 && <td className="num">{f.watts(at(power, seconds))}</td>}
              <td className="num">{f.bpm(at(hr, seconds))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function curveOption(power: CurvePoint[], hr: CurvePoint[]): ChartOption {
  const durations = [...new Set([...power, ...hr].map((p) => p.duration_s))].sort((a, b) => a - b)
  const series = (curve: CurvePoint[]) =>
    durations.map((d) => curve.find((p) => p.duration_s === d)?.value ?? null)
  return {
    animation: false,
    grid: { left: 60, right: 60, top: 40, bottom: 40 },
    legend: { top: 0 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: durations.map(f.shortDuration), boundaryGap: false },
    yAxis: [
      { type: 'value', name: 'W', show: power.length > 0 },
      { type: 'value', name: 'bpm', scale: true, show: hr.length > 0 },
    ],
    series: [
      ...(power.length
        ? [{ name: 'Power', type: 'line', data: series(power), yAxisIndex: 0 }]
        : []),
      ...(hr.length ? [{ name: 'Heart rate', type: 'line', data: series(hr), yAxisIndex: 1 }] : []),
    ],
  }
}
