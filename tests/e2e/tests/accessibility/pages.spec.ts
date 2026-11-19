import { test, expect } from '@playwright/test'
import { ComparePage } from '../../pageObjects/comparePage'
import { ImportPage } from '../../pageObjects/importPage'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { TrendsPage } from '../../pageObjects/trendsPage'
import { expectNoViolations } from '../../libs/accessibility'
import { RIDES, UPLOADS } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Every page scanned with axe (see libs/accessibility.ts), in light and dark mode.

// Read-only: a ride with every section, and one without power.
const FULL_RIDE = RIDES.INTERVALS
const NO_POWER = RIDES.HR_ONLY

// Light and dark from the system, and dark chosen in the app on a light system.
const THEMES = [
  { name: 'light mode', system: 'light', choose: false },
  { name: 'dark mode from the system', system: 'dark', choose: false },
  { name: 'dark mode chosen in the app', system: 'light', choose: true },
] as const

for (const theme of THEMES) {
  test(`every page passes an automated scan (${theme.name})`, async ({ page, request }) => {
    const library = new LibraryPage(page)
    const ride = new RidePage(page)
    const importPage = new ImportPage(page)
    const compare = new ComparePage(page)
    const trends = new TrendsPage(page)
    const testData = new TestData(request)
    await page.emulateMedia({ colorScheme: theme.system })

    await test.step('Library', async () => {
      await library.goto()
      // A light system starts light; one click switches to dark.
      if (theme.choose) await library.header.theme.click()
      await expect(library.rows.first()).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Library with no results', async () => {
      await library.goto({ q: 'nothing-matches-this' })
      await expect(library.count).toHaveText('No rides found.')
      await expectNoViolations(page)
    })

    await test.step('Ride with power', async () => {
      await ride.goto(await testData.rideId(FULL_RIDE.file))
      await expect(ride.traceChart).toBeVisible()
      await expect(ride.curveChart).toBeVisible()
      await expect(ride.similar.routeTable).toBeVisible()
      await ride.progress.showTable.click()
      await expect(ride.progress.table).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Ride with its similar efforts tab open', async () => {
      await ride.similar.effortTab.click()
      await expect(ride.similar.effortTable).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Ride with its details form open', async () => {
      await ride.editButton.click()
      await expect(ride.editForm).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Ride without power', async () => {
      await ride.goto(await testData.rideId(NO_POWER.file))
      await expect(ride.traceChart).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Compare, by distance and by time', async () => {
      await compare.goto([
        await testData.rideId(FULL_RIDE.file),
        await testData.rideId(NO_POWER.file),
      ])
      await expect(compare.gapChart).toBeVisible()
      await expect(compare.curves).toBeVisible()
      await expectNoViolations(page)
      await compare.alignTime.check()
      await expect(compare.gapChart).toBeHidden()
      await expectNoViolations(page)
    })

    await test.step('Compare with too few rides', async () => {
      await compare.goto([])
      await expect(compare.empty).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Trends, with every table shown', async () => {
      await trends.goto({ since: '2025-08-01', until: '2025-08-31' })
      await expect(trends.bestChart).toBeVisible()
      for (const section of [
        trends.fitness,
        trends.volume,
        trends.ftp,
        trends.efficiency,
        trends.best,
      ])
        await trends.showTable(section).click()
      await expect(trends.bestTable).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Trends with a range that ends before it starts', async () => {
      await trends.goto({ since: '2025-09-30', until: '2025-08-31' })
      await expect(trends.error).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Import, before and after importing', async () => {
      await importPage.goto()
      await expectNoViolations(page)
      // Already in the library, so nothing changes.
      await importPage.importFixtures(UPLOADS.EXPORT_ZIP)
      await expect(importPage.summary).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Bikes', async () => {
      await page.goto('/bikes')
      await expect(page.getByRole('heading', { name: 'Bikes', level: 1 })).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Settings', async () => {
      await page.goto('/settings')
      await expect(page.getByRole('heading', { name: 'Athlete' })).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Ride not found', async () => {
      await ride.goto('does-not-exist')
      await expect(ride.notFound).toBeVisible()
      await expectNoViolations(page)
    })

    await test.step('Page not found', async () => {
      await page.goto('/no-such-page')
      await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
      await expectNoViolations(page)
    })
  })
}
