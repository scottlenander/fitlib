import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { ImportPage } from '../../pageObjects/importPage'
import { RIDES } from '../../libs/constants'

// Read-only: the newest and oldest rides are listed; the interval ride is opened.
const NEWEST = RIDES.EXPORT_B.name
const OLDEST = RIDES.ZWIFT.name
const RIDE = RIDES.INTERVALS

test('a rider browses the library, opens a ride and finds the import page', async ({ page }) => {
  const library = new LibraryPage(page)
  const ride = new RidePage(page)
  const importPage = new ImportPage(page)

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
})
