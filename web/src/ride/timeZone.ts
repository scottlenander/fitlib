// Where a ride's local time came from, said in a sentence for the ride page.

export type TimeZoneSource = 'device' | 'file_name' | 'default' | 'none'

// The sentence, and when the default time zone is involved, the words leading to a link to
// Settings (where it is chosen): "<text> <settings> Settings."
export function timeZoneNote(
  source: TimeZoneSource,
  defaultZone: string | null | undefined,
): { text: string; settings: string | null } {
  switch (source) {
    case 'device':
      return { text: 'Local time from the device.', settings: null }
    case 'file_name':
      return { text: 'Local time from the file name.', settings: null }
    case 'default':
      return {
        text: `Time zone: your default (${(defaultZone ?? 'unknown').replaceAll('_', ' ')}), as the file doesn't say.`,
        settings: 'Change it in',
      }
    default:
      return {
        text: "Shown in UTC: the file doesn't say where it was ridden.",
        settings: 'Set a default time zone in',
      }
  }
}
