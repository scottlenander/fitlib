import { describe, expect, it } from 'vitest'
import { athleteValues, type AthleteFields } from './athleteForm'

const blank: AthleteFields = { from: '', ftp: '', weight: '', maxHr: '', thresholdHr: '' }

describe('athleteValues', () => {
  it('saves what was typed, leaving blank fields out', () => {
    const fields = { ...blank, from: '2025-08-01', ftp: '250', thresholdHr: ' ' }

    expect(athleteValues(fields, 'metric')).toEqual({
      from: '2025-08-01',
      values: { ftp: 250, weight_kg: null, max_hr: null, threshold_hr: null },
    })
  })

  it('turns pounds into kilograms, to the nearest 10 g', () => {
    const fields = { ...blank, from: '2025-08-01', weight: '150' }

    expect(athleteValues(fields, 'imperial')).toMatchObject({ values: { weight_kg: 68.04 } })
    expect(athleteValues(fields, 'metric')).toMatchObject({ values: { weight_kg: 150 } })
  })

  it('needs a date', () => {
    expect(athleteValues({ ...blank, ftp: '250' }, 'metric')).toEqual({
      error: 'Choose the date the values apply from.',
    })
  })

  it('needs at least one value', () => {
    expect(athleteValues({ ...blank, from: '2025-08-01' }, 'metric')).toEqual({
      error: 'Give at least one of FTP, weight, max or threshold heart rate.',
    })
  })
})
