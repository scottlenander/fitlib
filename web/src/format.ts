// Human-readable figures, as in fitlib's display.py. Every function takes SI values (as the
// API sends them) and returns text; missing values are shown as a dash.

export type Units = 'imperial' | 'metric'

export const DASH = '–'
const METRES_PER_MILE = 1609.344
const FEET_PER_METRE = 3.28084
const POUNDS_PER_KG = 2.20462
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

type Maybe = number | null | undefined

const pad = (n: number) => String(n).padStart(2, '0')
const fixed = (value: number, digits: number) => value.toFixed(digits)
const missing = (value: Maybe): value is null | undefined => value === null || value === undefined

// "42:05" under an hour, "1:02:05" from an hour up.
export function duration(seconds: Maybe): string {
  if (missing(seconds)) return DASH
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  return hours ? `${hours}:${pad(minutes)}:${pad(secs)}` : `${minutes}:${pad(secs)}`
}

export function distance(metres: Maybe, units: Units): string {
  if (missing(metres)) return DASH
  return units === 'imperial'
    ? `${fixed(metres / METRES_PER_MILE, 1)} mi`
    : `${fixed(metres / 1000, 1)} km`
}

export function speed(mps: Maybe, units: Units): string {
  if (missing(mps)) return DASH
  return units === 'imperial'
    ? `${fixed((mps * 3600) / METRES_PER_MILE, 1)} mph`
    : `${fixed(mps * 3.6, 1)} km/h`
}

export function elevation(metres: Maybe, units: Units): string {
  if (missing(metres)) return DASH
  return units === 'imperial' ? `${fixed(metres * FEET_PER_METRE, 0)} ft` : `${fixed(metres, 0)} m`
}

export function weight(kg: Maybe, units: Units): string {
  if (missing(kg)) return DASH
  return units === 'imperial' ? `${fixed(kg * POUNDS_PER_KG, 1)} lb` : `${fixed(kg, 1)} kg`
}

// Converts a speed or altitude sample for charts: mph/km/h and ft/m.
export function speedValue(mps: number, units: Units): number {
  return units === 'imperial' ? (mps * 3600) / METRES_PER_MILE : mps * 3.6
}

export function elevationValue(metres: number, units: Units): number {
  return units === 'imperial' ? metres * FEET_PER_METRE : metres
}

export const speedUnit = (units: Units) => (units === 'imperial' ? 'mph' : 'km/h')
export const elevationUnit = (units: Units) => (units === 'imperial' ? 'ft' : 'm')

export const watts = (value: Maybe) => (missing(value) ? DASH : `${fixed(value, 0)} W`)
export const bpm = (value: Maybe) => (missing(value) ? DASH : `${fixed(value, 0)} bpm`)
export const rpm = (value: Maybe) => (missing(value) ? DASH : `${fixed(value, 0)} rpm`)
export const kilojoules = (value: Maybe) => (missing(value) ? DASH : `${fixed(value, 0)} kJ`)
export const ratio = (value: Maybe) => (missing(value) ? DASH : fixed(value, 2))
export const tss = (value: Maybe) => (missing(value) ? DASH : fixed(value, 0))
export const wattsPerKg = (value: Maybe) => (missing(value) ? DASH : `${fixed(value, 2)} W/kg`)

export function signedPercent(value: Maybe): string {
  if (missing(value)) return DASH
  return `${value >= 0 ? '+' : '-'}${fixed(Math.abs(value), 1)} %`
}

// Splits an ISO time into its clock fields without converting time zones: local start
// times from the API have no zone, and UTC times end in "Z".
function fields(iso: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso)
  if (!match) throw new Error(`Not an ISO time: ${iso}`)
  const [year, month, day, hour, minute] = match.slice(1).map(Number) as [
    number,
    number,
    number,
    number,
    number,
  ]
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay()
  return { year, month, day, hour, minute, weekday }
}

// "Sat 02 Aug 2025, 08:30" on the rider's clock, or the UTC time with " UTC" when the
// device didn't record local time.
export function startTime(start: string, localStart: string | null | undefined): string {
  const f = fields(localStart ?? start)
  const text = `${DAYS[f.weekday]} ${pad(f.day)} ${MONTHS[f.month - 1]} ${f.year}, ${pad(f.hour)}:${pad(f.minute)}`
  return localStart ? text : `${text} UTC`
}

// "2025-08-02", from the local start when known.
export function date(start: string, localStart?: string | null): string {
  const f = fields(localStart ?? start)
  return `${f.year}-${pad(f.month)}-${pad(f.day)}`
}

// Curve and chart durations: "5 s", "1 min", "1 h", "1 h 30 min".
export function shortDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  return minutes ? `${hours} h ${minutes} min` : `${hours} h`
}
