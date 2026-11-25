// Saying where a ride's local time came from.
import { expect, test } from 'vitest'
import { timeZoneNote } from './timeZone'

test.each([
  ['device', null, 'Local time from the device.', null],
  ['file_name', null, 'Local time from the file name.', null],
  [
    'default',
    'America/New_York',
    "Time zone: your default (America/New York), as the file doesn't say.",
    'Change it in',
  ],
  [
    'none',
    null,
    "Shown in UTC: the file doesn't say where it was ridden.",
    'Set a default time zone in',
  ],
] as const)('%s', (source, zone, text, settings) => {
  expect(timeZoneNote(source, zone)).toEqual({ text, settings })
})
