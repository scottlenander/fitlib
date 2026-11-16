import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Read-only: rides opened to check what each part of the page shows.
const { INTERVALS, HR_ONLY, ZWIFT, INDOOR } = RIDES

test('a ride with power shows its figures, zones, best efforts and laps', async ({
  page,
  request,
}) => {
  const ride = new RidePage(page)

  await test.step('Open the interval ride', async () => {
    await ride.goto(await new TestData(request).rideId(INTERVALS.file))
    await expect(ride.heading).toHaveText(INTERVALS.name)
    await expect(ride.subtitle).toHaveText(
      'Tue 05 Aug 2025, 19:00 · Garmin · Garmin Edge 540 · Outdoor',
    )
  })

  await test.step('Summary', async () => {
    await expect(ride.summary.value('Moving time')).toHaveText('1:00:00')
    await expect(ride.summary.value('Distance')).toHaveText('19.9 mi')
    await expect(ride.summary.value('Climbing')).toHaveText('427 ft')
    await expect(ride.summary.value('NP')).toHaveText('230 W')
    await expect(ride.summary.value('Avg heart rate')).toHaveText('137 bpm')
  })

  await test.step('Training, with an estimated FTP', async () => {
    await expect(ride.training.value('FTP')).toHaveText('217 W (estimated)')
    await expect(ride.training.value('IF')).toHaveText('1.06')
    await expect(ride.training.value('TSS')).toHaveText('113')
    await expect(ride.training.value('Decoupling')).toHaveText('+3.6 %')
  })

  await test.step('Power zones; no heart-rate zones without a max heart rate', async () => {
    await expect(ride.zone(ride.powerZones, 'Z2')).toContainText('40:00')
    await expect(ride.zone(ride.powerZones, 'Z6')).toContainText('20:00')
    await expect(ride.hrZones, {
      message: 'Heart-rate zones need a max heart rate, which is not set',
    }).toBeHidden()
  })

  await test.step('Charts, best efforts and laps', async () => {
    await expect(ride.traceChart).toHaveAttribute('aria-label', /^Power, Heart rate, Cadence/)
    await expect(ride.curveChart).toBeVisible()
    await expect(ride.effort('20 min')).toContainText('228 W')
    await expect(ride.lapRows()).toHaveCount(12)
  })
})

test('a ride without power leaves out power figures', async ({ page, request }) => {
  const ride = new RidePage(page)

  await test.step('Open the heart-rate-only ride', async () => {
    await ride.goto(await new TestData(request).rideId(HR_ONLY.file))
    await expect(ride.heading).toHaveText(HR_ONLY.name)
  })

  await test.step('Heart rate is shown, power is not', async () => {
    await expect(ride.summary.value('Avg heart rate')).toHaveText('132 bpm')
    await expect(ride.summary.labels).not.toContainText(['NP'])
    await expect(ride.training.root, {
      message: 'Training figures need power, so the section should be hidden',
    }).toBeHidden()
    await expect(ride.powerZones, { message: 'No power, so no power zones' }).toBeHidden()
    await expect(ride.effort('20 min')).toContainText('132 bpm')
    await expect(ride.efforts.getByRole('columnheader', { name: 'Power' }), {
      message: 'The best-efforts table should have no power column',
    }).toBeHidden()
  })
})

test('a ride without local time shows its start in UTC', async ({ page, request }) => {
  const ride = new RidePage(page)

  await test.step('Open the Zwift ride', async () => {
    await ride.goto(await new TestData(request).rideId(ZWIFT.file))
  })

  await test.step('The start is marked UTC', async () => {
    await expect(ride.subtitle).toHaveText('Sat 02 Aug 2025, 06:30 UTC · Zwift · Zwift · Indoor')
  })
})

test('switching units changes the figures everywhere and is remembered', async ({
  page,
  request,
}) => {
  const ride = new RidePage(page)
  const library = new LibraryPage(page)

  await test.step('Open the indoor ride in imperial units (the default)', async () => {
    await ride.goto(await new TestData(request).rideId(INDOOR.file))
    await expect(ride.header.metricUnits, {
      message: 'Metric units should be off: the config says imperial',
    }).not.toBeChecked()
    await expect(ride.summary.value('Distance')).toHaveText('10.5 mi')
  })

  await test.step('Switch to metric', async () => {
    await ride.header.metricUnits.click()
    await expect(ride.summary.value('Distance')).toHaveText('17.0 km')
    await expect(ride.summary.value('Climbing')).toHaveText('70 m')
  })

  await test.step('Still metric after a reload, and in the library', async () => {
    await page.reload()
    await expect(ride.summary.value('Distance')).toHaveText('17.0 km')
    await ride.header.libraryLink.click()
    await expect(library.row(INDOOR.name)).toContainText('17.0 km')
  })
})

test('a ride that does not exist says so', async ({ page }) => {
  const ride = new RidePage(page)

  await test.step('Open a ride id nobody has', async () => {
    await ride.goto('does-not-exist')
  })

  await test.step('Not found, with a way back', async () => {
    await expect(ride.notFound).toBeVisible()
    await ride.backToLibrary.click()
    await expect(page).toHaveURL(/\/$/)
  })
})
