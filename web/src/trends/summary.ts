// The trends page's summary: where fitness, fatigue, form and FTP stand at the end of a range.
import type { FitnessDay, Ftp } from '../api/trends'
import type { Stat } from '../shared/Stats'
import * as f from '../shared/format'

// A whole number with its sign: form above zero is fresh, below is tired.
export const signed = (value: number) => `${value > 0.5 ? '+' : ''}${value.toFixed(0)}`

// The figures over the charts: fitness, fatigue and form on the range's last day, its total
// TSS, and the set and estimated FTP at its end. Dashes where there's nothing yet.
export function trendSummary(days: FitnessDay[], ftp: Ftp['points']): Stat[] {
  const last = days[days.length - 1]
  const lastFtp = ftp[ftp.length - 1]
  return [
    { label: 'Fitness', value: last ? last.fitness.toFixed(0) : f.DASH, note: 'CTL' },
    { label: 'Fatigue', value: last ? last.fatigue.toFixed(0) : f.DASH, note: 'ATL' },
    { label: 'Form', value: last ? signed(last.form) : f.DASH, note: 'TSB' },
    { label: 'TSS', value: f.tss(days.reduce((sum, d) => sum + d.tss, 0)), note: 'in range' },
    { label: 'FTP', value: f.watts(lastFtp?.ftp) },
    { label: 'Estimated FTP', value: f.watts(lastFtp?.estimated) },
  ]
}
