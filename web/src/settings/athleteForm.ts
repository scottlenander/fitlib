// What's typed in the athlete form, turned into the values to save.
import type { AthleteValues } from '../api/athlete'
import * as f from '../shared/format'

export type AthleteFields = {
  from: string
  ftp: string
  weight: string
  maxHr: string
  thresholdHr: string
}

// A number typed in a field, or null for a blank one.
const number = (text: string) => (text.trim() === '' ? null : Number(text))

// The values to save from a date (weight in kg, to the nearest 10 g), or why they can't be.
export function athleteValues(
  fields: AthleteFields,
  units: f.Units,
): { from: string; values: AthleteValues } | { error: string } {
  const kg = number(fields.weight)
  const values: AthleteValues = {
    ftp: number(fields.ftp),
    weight_kg: kg === null ? null : Math.round(f.kgFrom(kg, units) * 100) / 100,
    max_hr: number(fields.maxHr),
    threshold_hr: number(fields.thresholdHr),
  }
  if (!fields.from) return { error: 'Choose the date the values apply from.' }
  if (Object.values(values).every((v) => v === null))
    return { error: 'Give at least one of FTP, weight, max or threshold heart rate.' }
  return { from: fields.from, values }
}
