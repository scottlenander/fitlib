import { describe, expect, it } from 'vitest'
import type { FitnessDay, Ftp } from '../api/trends'
import { DASH } from '../shared/format'
import { signed, trendSummary } from './summary'

const day = (
  d: string,
  fitness: number,
  fatigue: number,
  form: number,
  tss: number,
): FitnessDay => ({ day: d, fitness, fatigue, form, tss })
const point = (d: string, ftp: number | null, estimated: number | null): Ftp['points'][number] => ({
  day: d,
  ftp,
  estimated,
})

const values = (stats: { label: string; value: string }[]) =>
  Object.fromEntries(stats.map((s) => [s.label, s.value]))

describe('trendSummary', () => {
  it('takes fitness, fatigue and form from the last day, and adds up TSS', () => {
    const days = [day('2025-08-01', 40, 50, -5, 80), day('2025-08-02', 42.4, 47.6, -10.2, 60)]

    expect(values(trendSummary(days, []))).toMatchObject({
      Fitness: '42',
      Fatigue: '48',
      Form: '-10',
      TSS: '140',
    })
  })

  it('takes the set and estimated FTP at the end of the range', () => {
    const ftp = [point('2025-08-03', 240, 231), point('2025-08-10', 250, null)]

    expect(values(trendSummary([], ftp))).toMatchObject({ FTP: '250 W', 'Estimated FTP': DASH })
  })

  it('shows dashes with no data yet', () => {
    const shown = values(trendSummary([], []))

    expect([shown.Fitness, shown.Fatigue, shown.Form, shown.FTP]).toEqual([DASH, DASH, DASH, DASH])
  })
})

describe('signed', () => {
  it('puts a plus on fresh form and keeps the minus on tired', () => {
    expect([signed(12.3), signed(-4.6), signed(0)]).toEqual(['+12', '-5', '0'])
  })
})
