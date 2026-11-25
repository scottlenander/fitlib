// The trends charts, loaded (with ECharts) only when a page shows one, and the fallback
// while they load.
import { lazy, Suspense, type ReactNode } from 'react'

const charts = () => import('./TrendCharts')
export const FitnessChart = lazy(() => charts().then((m) => ({ default: m.FitnessChart })))
export const VolumeChart = lazy(() => charts().then((m) => ({ default: m.VolumeChart })))
export const FtpChart = lazy(() => charts().then((m) => ({ default: m.FtpChart })))
export const EfficiencyChart = lazy(() => charts().then((m) => ({ default: m.EfficiencyChart })))
export const BestCurveChart = lazy(() => charts().then((m) => ({ default: m.BestCurveChart })))

export function Chart({ children }: { children: ReactNode }) {
  return <Suspense fallback={<p>Loading chart…</p>}>{children}</Suspense>
}
