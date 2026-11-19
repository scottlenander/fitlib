import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { SettingsPage } from '../../pageObjects/settingsPage'
import { expectNoViolations } from '../../libs/accessibility'
import { EXTRA, EXTRA_DIR, FIXTURES_DIR, RIDES, UPLOADS } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// This spec owns the watched folders. Each test watches a new folder of its own in the temp
// folder (in e2e mode only folders there can be watched) and stops watching it at the end;
// checks only look at that folder, so copies of a test can run side by side. The extra ride
// is deleted first, then dropped into the folder and imported by the server's watcher (once
// it has stopped changing for 10 s, then shown within the 5 s Settings checks).
const WATCHED = EXTRA.WATCHED
// Already in the library at start-up: found again, and left out of the latest files.
const ALREADY = RIDES.ZWIFT
const IMPORT_TIMEOUT = 40_000

// One at a time: the first test's import mustn't land while the second checks that nothing
// new is announced. There's one extra ride, so copies of the first test can't overlap
// either: check re-runs with --repeat-each=3 --workers=1 (CI runs one worker anyway).
test.describe.configure({ mode: 'serial' })

const PREFIX = 'fitlib-watch-'

// A new empty folder to watch, inside the temp folder.
function newFolder(): string {
  return fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), PREFIX)))
}

// Stopping watching is tested in the UI below; this only clears up after a failed run.
test.beforeEach(async ({ request }) => {
  await new TestData(request).stopWatchingLeftovers(PREFIX)
})

test('a ride dropped into a watched folder is imported, announced and opened', async ({
  page,
  request,
}) => {
  const settings = new SettingsPage(page)
  const ride = new RidePage(page)
  const library = new LibraryPage(page)
  const testData = new TestData(request)
  const folder = newFolder()

  await test.step('Start without the extra ride', async () => {
    const id = await testData.findRideId(WATCHED.file)
    if (id) await testData.deleteRide(id)
  })

  await test.step('Watch a new folder', async () => {
    await settings.goto()
    await settings.watchFolder(folder)
    await expect(settings.watchNotice).toHaveText(
      `Watching ${folder}. Rides already in it are being imported.`,
    )
    await expect(settings.watchedFolder(folder)).toContainText('Watching')
    await expect(settings.watchedFolder(folder)).toContainText('0 files found')
    await expect(settings.folderToWatch, {
      message: 'The field should be cleared for the next folder',
    }).toHaveValue('')
  })

  await test.step('Drop a ride into it: it is imported once it settles', async () => {
    fs.copyFileSync(path.join(EXTRA_DIR, WATCHED.file), path.join(folder, WATCHED.file))
    await expect(settings.latestFile(WATCHED.file)).toContainText('Imported', {
      timeout: IMPORT_TIMEOUT,
    })
    await expect(settings.watchedFolder(folder)).toContainText('1 file found')
  })

  await test.step('The new ride is announced, and opens', async () => {
    await expect(settings.newRides.root).toHaveText(
      '1 new ride imported from a watched folder. Open it Dismiss',
    )
    await expectNoViolations(page)
    await settings.newRides.open.click()
    await expect(ride.heading).toHaveText(WATCHED.name)
  })

  await test.step('Dismissed, the notice stays away', async () => {
    await settings.newRides.dismiss.click()
    await expect(settings.newRides.root, {
      message: 'A dismissed notice should not come back for the same ride',
    }).toBeHidden()
  })

  await test.step('Stop watching: the ride stays in the library', async () => {
    await settings.goto()
    await settings.stopWatching(folder).click()
    await expect(settings.watchedFolder(folder)).toHaveCount(0)
    await library.goto({ since: '2025-08-07', until: '2025-08-07' })
    await expect(library.row(WATCHED.name)).toBeVisible()
  })
})

test('Scan now finds what is in a folder; rides already there are not listed', async ({ page }) => {
  const settings = new SettingsPage(page)
  const folder = newFolder()
  // Written long ago, so a scan takes them at once rather than waiting for them to settle.
  for (const file of [ALREADY.file, UPLOADS.CORRUPT]) {
    fs.copyFileSync(path.join(FIXTURES_DIR, file), path.join(folder, file))
    fs.utimesSync(path.join(folder, file), new Date(2025, 0, 1), new Date(2025, 0, 1))
  }

  await test.step('Watch the folder and scan it', async () => {
    await settings.goto()
    await settings.watchFolder(folder)
    await expect(settings.watchedFolder(folder)).toBeVisible()
    await settings.scanNow.click()
    await expect(settings.scanResult).toHaveText('Looking for new rides in the watched folders…')
  })

  await test.step('The broken file is listed; the ride already in the library is not', async () => {
    await expect(settings.latestFile(UPLOADS.CORRUPT)).toContainText("Couldn't be read", {
      timeout: IMPORT_TIMEOUT,
    })
    await expect(settings.watchedFolder(folder)).toContainText('2 files found')
    await expect(settings.latestFile(ALREADY.file), {
      message: 'A ride already in the library should not be listed as new',
    }).toHaveCount(0)
    await expect(settings.newRides.root, {
      message: 'Nothing new was imported, so nothing should be announced',
    }).toBeHidden()
  })

  await test.step('On a phone, the long path wraps rather than widening the page', async () => {
    await page.setViewportSize({ width: 390, height: 844 })
    const scrollsSideways = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    )
    expect(scrollsSideways, 'the Settings page should fit a phone screen').toBe(false)
    await expectNoViolations(page)
  })

  await test.step('Clean up', async () => {
    await settings.stopWatching(folder).click()
    await expect(settings.watchedFolder(folder)).toHaveCount(0)
  })
})

test('folders that cannot be watched are refused with the reason', async ({ page }) => {
  const settings = new SettingsPage(page)
  const missing = path.join(os.tmpdir(), 'fitlib-watch-no-such-folder')

  await test.step('A path that is not a full path', async () => {
    await settings.goto()
    await settings.watchFolder('Activities')
    await expect(settings.watchError).toContainText("Give the folder's full path")
  })

  await test.step('A folder that does not exist', async () => {
    await settings.watchFolder(missing)
    await expect(settings.watchError).toContainText("There's no folder at")
  })

  await test.step('A folder outside the temp folder (e2e mode keeps to it)', async () => {
    await settings.watchFolder(FIXTURES_DIR)
    await expect(settings.watchError).toContainText('Only folders inside')
    await expect(settings.watchedFolder(FIXTURES_DIR), {
      message: 'Nothing should have been added',
    }).toHaveCount(0)
    await expect(settings.folderToWatch, {
      message: 'The path should stay, to be corrected',
    }).toHaveValue(FIXTURES_DIR)
  })
})
