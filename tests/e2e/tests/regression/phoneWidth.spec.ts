import { test, expect, type Page } from '@playwright/test'
import { ComparePage } from '../../pageObjects/comparePage'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { expectNoViolations } from '../../libs/accessibility'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Read-only: pages with wide tables, opened on a phone-sized screen. Wide tables scroll
// inside their own box; the page itself never scrolls sideways, and a keyboard can reach
// every box that scrolls (checked by the accessibility scan).
const { INTERVALS, EXPORT_A, EXPORT_B } = RIDES

test.use({ viewport: { width: 390, height: 844 } })

// Whether the page is wider than the screen.
function pageScrollsSideways(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
}

test('pages fit a phone screen, with wide tables scrolling on their own, by keyboard too', async ({
  page,
  request,
}) => {
  const library = new LibraryPage(page)
  const ride = new RidePage(page)
  const compare = new ComparePage(page)
  const testData = new TestData(request)

  await test.step('Library', async () => {
    await library.goto()
    await expect(library.rows.first()).toBeVisible()
    expect(await pageScrollsSideways(page), 'the library should fit the screen').toBe(false)
    await expectNoViolations(page)
  })

  await test.step('A ride with zones, laps and similar rides', async () => {
    await ride.goto(await testData.rideId(INTERVALS.file))
    await expect(ride.similar.routeTable).toBeVisible()
    await expect(ride.laps).toBeVisible()
    expect(await pageScrollsSideways(page), 'the ride page should fit the screen').toBe(false)
    await expectNoViolations(page)
  })

  await test.step('Comparing two rides', async () => {
    await compare.goto([await testData.rideId(EXPORT_A.file), await testData.rideId(EXPORT_B.file)])
    await expect(compare.table).toBeVisible()
    expect(await pageScrollsSideways(page), 'the compare page should fit the screen').toBe(false)
    await expectNoViolations(page)
  })
})
