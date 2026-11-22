// How TSS is marked as estimated or from heart rate.
import { describe, expect, test } from 'vitest'
import { tssNotes, tssText, type TssFigures } from './tss'

const fmt = (tss: number | null) => (tss === null ? '–' : String(Math.round(tss)))
const ride = (changes: Partial<TssFigures>): TssFigures => ({
  tss: 100,
  tss_source: 'power',
  ftp_estimated: false,
  threshold_hr_estimated: false,
  ...changes,
})

describe('TSS text', () => {
  test.each([
    ['set FTP', ride({}), '100'],
    ['estimated FTP', ride({ ftp_estimated: true }), '100*'],
    ['heart rate, set threshold', ride({ tss: 48, tss_source: 'hr' }), '48 HR'],
    [
      'heart rate, threshold from age',
      ride({ tss: 52, tss_source: 'hr', threshold_hr_estimated: true }),
      '52 HR*',
    ],
    ['no TSS', ride({ tss: null, tss_source: null, ftp_estimated: true }), '–'],
  ])('%s', (_, figures, text) => {
    expect(tssText(figures, fmt)).toBe(text)
  })

  test('an estimated FTP does not star a heart-rate TSS', () => {
    expect(tssText(ride({ tss_source: 'hr', ftp_estimated: true }), fmt)).toBe('100 HR')
  })
})

describe('TSS notes', () => {
  test('nothing to explain', () => {
    expect(tssNotes([ride({}), ride({ tss: null, tss_source: null })])).toEqual([])
  })

  test('each mark used is explained once', () => {
    expect(
      tssNotes([
        ride({ ftp_estimated: true }),
        ride({ tss_source: 'hr', threshold_hr_estimated: true }),
        ride({ tss_source: 'hr' }),
      ]),
    ).toEqual([
      '* TSS from an estimated FTP (no FTP set for that date).',
      'HR: TSS from heart rate, as the ride has no power. * on those: threshold heart rate not set, so worked out from your rides or your age.',
    ])
  })

  test('heart rate with set thresholds only', () => {
    expect(tssNotes([ride({ tss_source: 'hr' })])).toEqual([
      'HR: TSS from heart rate, as the ride has no power.',
    ])
  })
})
