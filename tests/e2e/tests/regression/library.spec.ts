import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RIDES } from '../../libs/constants'

// Read-only. Counts and paging only use rides from 10 Aug on, leaving out the 9 Aug ride
// that the import spec deletes and imports again.
const SINCE_10_AUG = { since: '2025-08-10' }
const { ZWIFT, INTERVALS, SMART, HR_ONLY, INDOOR, EXPORT_A, EXPORT_B } = RIDES

test('searching finds rides by their device, and an empty result says so', async ({ page }) => {
  const library = new LibraryPage(page)

  await test.step('Search for "zwift"', async () => {
    await library.goto()
    await library.searchFor('zwift')
    await expect(library.rideNames()).toHaveText([ZWIFT.name])
    await expect(library.count).toHaveText('Showing 1–1 of 1 ride')
    await expect(page, { message: 'The search should be kept in the URL' }).toHaveURL(/q=zwift/)
  })

  await test.step('Search for something no ride has', async () => {
    await library.searchFor('nothing-matches-this')
    await expect(library.count).toHaveText('No rides found.')
    await expect(library.table, { message: 'An empty result should have no table' }).toBeHidden()
  })

  await test.step('Clear the search', async () => {
    await library.clearFilters.click()
    await expect(library.search).toHaveValue('')
    await expect(library.row(EXPORT_B.name)).toBeVisible()
  })
})

test('each filter narrows the list to the matching rides', async ({ page }) => {
  const library = new LibraryPage(page)

  await test.step('Source: Zwift', async () => {
    await library.goto()
    await library.source.selectOption({ label: 'Zwift' })
    await expect(library.rideNames()).toHaveText([ZWIFT.name])
  })

  await test.step('Where: indoor', async () => {
    await library.clearFilters.click()
    await library.where.selectOption({ label: 'Indoor' })
    await expect(library.rideNames()).toHaveText([INDOOR.name, ZWIFT.name])
  })

  await test.step('Power: without power', async () => {
    await library.clearFilters.click()
    await library.power.selectOption({ label: 'Without power' })
    await expect(library.rideNames()).toHaveText([HR_ONLY.name])
  })

  await test.step('Dates: 16 to 19 Aug, both days included', async () => {
    await library.clearFilters.click()
    await library.from.fill('2025-08-16')
    await library.to.fill('2025-08-19')
    await expect(library.rideNames()).toHaveText([INDOOR.name, HR_ONLY.name])
  })

  await test.step('At least 60 minutes', async () => {
    await library.clearFilters.click()
    await library.minMinutes.fill('60')
    await expect(library.rideNames()).toHaveText([INTERVALS.name, ZWIFT.name])
  })

  await test.step('Filters combine', async () => {
    await library.source.selectOption({ label: 'Garmin' })
    await expect(library.rideNames()).toHaveText([INTERVALS.name])
  })
})

test('sorting by a column, then the other way', async ({ page }) => {
  const library = new LibraryPage(page)

  await test.step('Newest first to start with', async () => {
    await library.goto(SINCE_10_AUG)
    await expect(library.columnHeader('Date')).toHaveAttribute('aria-sort', 'descending')
    await expect(library.rideNames().first()).toHaveText(EXPORT_B.name)
  })

  await test.step('Sort by riding time, longest first', async () => {
    await library.sortButton('Time').click()
    await expect(library.columnHeader('Time')).toHaveAttribute('aria-sort', 'descending')
    await expect(library.rideNames().first()).toHaveText(HR_ONLY.name)
    await expect(library.rideNames().last()).toHaveText(EXPORT_A.name)
  })

  await test.step('Sort the other way, shortest first', async () => {
    await library.sortButton('Time').click()
    await expect(library.columnHeader('Time')).toHaveAttribute('aria-sort', 'ascending')
    await expect(library.rideNames().first()).toHaveText(EXPORT_A.name)
    await expect(library.rideNames().last()).toHaveText(HR_ONLY.name)
    await expect(library.columnHeader('Date'), {
      message: 'Only the sorted column should say it is sorted',
    }).toHaveAttribute('aria-sort', 'none')
  })
})

test('paging through rides, kept in the URL across a reload', async ({ page }) => {
  const library = new LibraryPage(page)

  await test.step('Two rides a page', async () => {
    await library.goto({ ...SINCE_10_AUG, limit: '2' })
    await expect(library.rideNames()).toHaveText([EXPORT_B.name, EXPORT_A.name])
    await expect(library.pageStatus(1, 3)).toBeVisible()
    await expect(library.previous, { message: 'There is no page before the first' }).toBeDisabled()
  })

  await test.step('Next page', async () => {
    await library.next.click()
    await expect(library.rideNames()).toHaveText([INDOOR.name, HR_ONLY.name])
    await expect(library.count).toHaveText('Showing 3–4 of 5 rides')
  })

  await test.step('Reload: still on page 2', async () => {
    await page.reload()
    await expect(library.pageStatus(2, 3)).toBeVisible()
    await expect(library.rideNames()).toHaveText([INDOOR.name, HR_ONLY.name])
  })

  await test.step('Last page', async () => {
    await library.next.click()
    await expect(library.rideNames()).toHaveText([SMART.name])
    await expect(library.next, { message: 'There is no page after the last' }).toBeDisabled()
  })

  await test.step('More rides a page goes back to page 1', async () => {
    await library.perPage.selectOption('10')
    await expect(library.pageStatus(1, 1)).toBeVisible()
    await expect(library.rows).toHaveCount(5)
  })
})

test('TSS from an estimated FTP is marked', async ({ page }) => {
  const library = new LibraryPage(page)

  await test.step('Open the library (no FTP has been set)', async () => {
    await library.goto()
  })

  await test.step('The interval ride shows its TSS with a mark and a note', async () => {
    await expect(library.row(INTERVALS.name)).toContainText('113*')
    await expect(library.estimatedNote).toBeVisible()
  })
})
