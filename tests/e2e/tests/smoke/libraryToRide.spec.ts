import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { ImportPage } from '../../pageObjects/importPage'
import { ComparePage } from '../../pageObjects/comparePage'
import { TrendsPage } from '../../pageObjects/trendsPage'
import { RIDES } from '../../libs/constants'

// Read-only: the newest and oldest rides are listed; the interval ride is opened, then
// compared with the newest.
const NEWEST = RIDES.EXPORT_B.name
const OLDEST = RIDES.ZWIFT.name
const RIDE = RIDES.INTERVALS

test('a rider browses the library, opens a ride, finds the import page, compares rides and sees trends', async ({
  page,
}) => {
  const library = new LibraryPage(page)
  const ride = new RidePage(page)
  const importPage = new ImportPage(page)
  const compare = new ComparePage(page)
  const trends = new TrendsPage(page)

  await test.step('Open the library', async () => {
    await library.goto()
    await expect(library.heading).toBeVisible()
    await expect(library.rideNames().first()).toHaveText(NEWEST)
    await expect(library.row(OLDEST)).toBeVisible()
  })

  await test.step('Open a ride', async () => {
    await library.rideLink(RIDE.name).click()
    await expect(ride.heading).toHaveText(RIDE.name)
    await expect(ride.summary.value('Distance')).toHaveText('19.9 mi')
    await expect(ride.training.value('TSS')).toHaveText('113')
    await expect(ride.traceChart, {
      message: 'The chart of the ride should be drawn',
    }).toBeVisible()
  })

  await test.step('Back to the library from the header', async () => {
    await ride.header.libraryLink.click()
    await expect(library.heading).toBeVisible()
  })

  await test.step('Go to the import page', async () => {
    await library.header.importLink.click()
    await expect(importPage.heading).toBeVisible()
    await expect(importPage.importButton, {
      message: 'Import should wait until files are chosen',
    }).toBeDisabled()
  })

  await test.step('Compare the ride with the newest one', async () => {
    await importPage.header.libraryLink.click()
    await library.pick(RIDE.name).check()
    await library.pick(NEWEST).check()
    await library.compareButton.click()
    await expect(compare.rides).toHaveCount(2)
    await expect(compare.traces, {
      message: 'The overlaid charts should be drawn',
    }).toBeVisible()
  })
  await test.step('See trends over the fixture rides', async () => {
    await compare.header.trendsLink.click()
    await trends.preset('All').check()
    await expect(trends.rangeText).toContainText('Sat 02 Aug 2025 to')
    await expect(trends.fitnessChart, {
      message: 'The fitness chart should be drawn',
    }).toBeVisible()
    await expect(trends.volumeChart).toBeVisible()
  })
})
