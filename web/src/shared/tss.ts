// How a ride's TSS is marked: " HR" when it comes from heart rate (rides without power), and
// "*" when the FTP or threshold heart rate behind it is estimated.

export type TssFigures = {
  tss: number | null
  tss_source?: 'power' | 'hr' | null
  ftp_estimated: boolean
  threshold_hr_estimated: boolean
}

export type TssMarks = { fromHeartRate: boolean; estimated: boolean }

export function tssMarks(r: TssFigures): TssMarks {
  if (r.tss === null) return { fromHeartRate: false, estimated: false }
  const fromHeartRate = r.tss_source === 'hr'
  return {
    fromHeartRate,
    estimated: fromHeartRate ? r.threshold_hr_estimated : r.ftp_estimated,
  }
}

// The marks as text, e.g. "112*", "48 HR", "52 HR*" (for tables without room for more).
export function tssText(r: TssFigures, format: (tss: number | null) => string): string {
  const { fromHeartRate, estimated } = tssMarks(r)
  return format(r.tss) + (fromHeartRate ? ' HR' : '') + (estimated ? '*' : '')
}

// The footnotes explaining the marks used in a list of rides; empty when none were.
export function tssNotes(rides: TssFigures[]): string[] {
  const marks = rides.map(tssMarks)
  const notes: string[] = []
  if (marks.some((m) => m.estimated && !m.fromHeartRate))
    notes.push('* TSS from an estimated FTP (no FTP set for that date).')
  if (marks.some((m) => m.fromHeartRate)) {
    const estimated = marks.some((m) => m.fromHeartRate && m.estimated)
      ? ' * on those: threshold heart rate not set, so worked out from your rides or your age.'
      : ''
    notes.push(`HR: TSS from heart rate, as the ride has no power.${estimated}`)
  }
  return notes
}

// Where a threshold heart rate came from, said after its value; nothing for one that was set.
export const THRESHOLD_NOTES: Record<'set' | 'rides' | 'age', string | undefined> = {
  set: undefined,
  rides: '(from your rides)',
  age: '(estimated from age)',
}
