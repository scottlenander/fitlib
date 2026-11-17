import path from 'node:path'

// The fixture rides (tests/fixtures/fit/, imported into a fresh library by scripts/e2e-server).
//
// Tests that CHANGE a ride (edit it, delete it, re-import it) must each use their own ride,
// so tests never interfere and can be re-run safely. Before using a ride in a test, check
// `usedBy` here; claim a free one if you will change it. Tests that count rides or page
// through the library must leave out rides that another spec changes (use a date filter).
//
// Global settings are claimed the same way: the bikes spec owns the "indoor" default-bike
// slot, the athlete spec owns athlete entries dated 2026 (after every fixture ride, so
// no ride's FTP changes), and the time zone spec owns the default time zone (which only
// moves the NO_TIME_ZONE ride). Bikes can't be deleted, so specs name theirs with a per-run suffix.
//
// - file: the ride's source file name, for looking up its id (ids are random each run).
// - usedBy: spec files that use it. `changes: true` means a test modifies it.
// Figures are as the app shows them in imperial units (the e2e server's config).

export type FixtureRide = {
  readonly file: string
  readonly name: string
  readonly date: string
  readonly changes: boolean
  readonly usedBy: readonly string[]
}

export const RIDES = {
  ZWIFT: {
    file: '2025-08-02-08-29-42.fit',
    name: 'Zwift 2025-08-02 08:30',
    date: '2025-08-02',
    changes: false,
    usedBy: [
      'regression/compare.spec.ts',
      'smoke/libraryToRide.spec.ts',
      'regression/library.spec.ts',
      'regression/rideDetail.spec.ts',
      'regression/similarRides.spec.ts',
      'accessibility/pages.spec.ts',
    ],
  },
  INTERVALS: {
    file: 'garmin_nord_intervals_5x4.fit',
    name: 'Garmin 2025-08-05 19:00',
    date: '2025-08-05',
    changes: false,
    usedBy: [
      'regression/phoneWidth.spec.ts',
      'regression/rideStats.spec.ts',
      'regression/compare.spec.ts',
      'regression/similarRides.spec.ts',
      'smoke/libraryToRide.spec.ts',
      'regression/library.spec.ts',
      'regression/rideDetail.spec.ts',
      'accessibility/pages.spec.ts',
    ],
  },
  PAUSE: {
    file: 'garmin_nord_pause_10min.fit',
    name: 'Garmin 2025-08-09 10:00',
    date: '2025-08-09',
    // Deleted and imported again through the import page.
    changes: true,
    usedBy: ['regression/import.spec.ts'],
  },
  SMART: {
    file: 'garmin_nord_smart_recording.fit',
    name: 'Garmin 2025-08-12 20:00',
    date: '2025-08-12',
    // Renamed, tagged, rated and given a bike; reset to no edits at the start.
    changes: true,
    usedBy: ['regression/rideEdits.spec.ts'],
  },
  HR_ONLY: {
    file: 'garmin_nord_hr_no_power.fit',
    name: 'Garmin 2025-08-16 11:00',
    date: '2025-08-16',
    changes: false,
    usedBy: [
      'regression/compare.spec.ts',
      'regression/similarRides.spec.ts',
      'regression/library.spec.ts',
      'regression/rideDetail.spec.ts',
      'accessibility/pages.spec.ts',
    ],
  },
  INDOOR: {
    file: 'garmin_indoor_no_hr.fit',
    name: 'Garmin indoor 2025-08-19 20:30',
    date: '2025-08-19',
    // Gets the bike spec's default bike for indoor rides (the only ride that default affects).
    // The other specs only read figures the bike doesn't change.
    changes: true,
    usedBy: [
      'regression/similarRides.spec.ts',
      'regression/bikes.spec.ts',
      'regression/library.spec.ts',
      'regression/rideDetail.spec.ts',
    ],
  },
  EXPORT_A: {
    file: 'garmin_export_ride_a.fit',
    name: 'Garmin 2025-08-23 09:00',
    date: '2025-08-23',
    changes: false,
    usedBy: [
      'regression/phoneWidth.spec.ts',
      'regression/compare.spec.ts',
      'regression/similarRides.spec.ts',
      'regression/library.spec.ts',
    ],
  },
  NO_TIME_ZONE: {
    file: 'other_ride_no_time_zone.fit',
    // Named for its start in UTC; in the default time zone once one is set.
    name: 'Ride 2025-08-11 02:00 UTC',
    date: '2025-08-11',
    // Its date and time follow the default time zone, which the time zone spec changes.
    changes: true,
    usedBy: ['regression/timeZone.spec.ts'],
  },
  EXPORT_B: {
    file: 'garmin_export_ride_b.fit',
    name: 'Garmin 2025-08-24 09:00',
    date: '2025-08-24',
    changes: false,
    usedBy: [
      'regression/phoneWidth.spec.ts',
      'regression/compare.spec.ts',
      'regression/similarRides.spec.ts',
      'smoke/libraryToRide.spec.ts',
      'regression/library.spec.ts',
    ],
  },
} as const satisfies Record<string, FixtureRide>

// Fixture files that are never in the library, for uploads.
export const FIXTURES_DIR = path.join(__dirname, '..', '..', 'fixtures', 'fit')
export const UPLOADS = {
  // Fails: cut off part-way through.
  CORRUPT: 'corrupt_truncated.fit',
  // Skipped: a run, not a ride.
  RUN: 'garmin_nord_run_20min.fit',
  // Skipped: a second recording of the Zwift ride.
  OVERLAP: 'zwift_watopia_steady_60min_head_unit.fit',
  // Already in the library: both rides inside it are imported at start-up.
  EXPORT_ZIP: 'garmin_export.zip',
} as const
