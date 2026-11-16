import { test, expect, type Page } from '@playwright/test'
import { AxeBuilder } from '@axe-core/playwright'
import { ImportPage } from '../../pageObjects/importPage'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { RIDES, UPLOADS } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Automated WCAG 2.2 AA checks (axe-core) on every page. These catch about a third of
// accessibility problems, such as missing labels, low contrast and broken ARIA. Keyboard
// and screen reader checks still need a person.
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

// Read-only: a ride with every section, and one without power.
const FULL_RIDE = RIDES.INTERVALS
const NO_POWER = RIDES.HR_ONLY

// Scans the page as it is now. On failure, lists each problem and where it is.
async function expectNoViolations(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
  const summary = violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help} at ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
  )
  expect(summary, `accessibility problems on ${page.url()}`).toEqual([])
}

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
    const testData = new TestData(request)
    await page.emulateMedia({ colorScheme: theme.system })

    await test.step('Library', async () => {
      await library.goto()
      if (theme.choose) await library.header.darkMode.click()
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
