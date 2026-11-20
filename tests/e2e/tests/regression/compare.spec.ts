import { test, expect } from '@playwright/test'
import { ComparePage } from '../../pageObjects/comparePage'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Read-only: rides are compared, never changed. The library is narrowed to rides from 13 Aug
// on, which leaves out rides other specs change (12 Aug renamed, 9 Aug re-imported).
const { ZWIFT, INTERVALS, HR_ONLY, EXPORT_A, EXPORT_B } = RIDES
const SINCE_13_AUG = { since: '2025-08-13' }

test('pick two rides in the library and compare them', async ({ page }) => {
  const library = new LibraryPage(page)
  const compare = new ComparePage(page)

  await test.step('Open the library from 13 Aug', async () => {
    await library.goto(SINCE_13_AUG)
    await expect(library.row(EXPORT_A.name)).toBeVisible()
    await expect(library.compareButton, {
      message: 'Compare should wait until 2 rides are picked',
    }).toBeDisabled()
  })

  await test.step('Pick the two exported rides', async () => {
    await library.pick(EXPORT_A.name).check()
    await expect(library.compareButton, {
      message: 'One ride is not enough to compare',
    }).toBeDisabled()
    await library.pick(EXPORT_B.name).check()
    await expect(library.selectionStatus).toHaveText(
      `Selected: ${EXPORT_A.name}, ${EXPORT_B.name}.`,
    )
    await expect(library.compareButton).toHaveText('Compare (2)')
  })

  await test.step('Compare them', async () => {
    await library.compareButton.click()
    await expect(compare.heading).toBeVisible()
    await expect(compare.rides).toHaveCount(2)
    await expect(compare.columnHeads()).toHaveText([EXPORT_A.name, EXPORT_B.name])
  })

  await test.step('Their figures are side by side', async () => {
    await expect(compare.figure('Distance', 0)).toHaveText('6.4 mi')
    await expect(compare.figure('Distance', 1)).toHaveText('8.3 mi')
    await expect(compare.figure('Best 20 min', 0)).toHaveText('160 W')
    await expect(compare.figure('Best 20 min', 1)).toHaveText('175 W')
  })

  await test.step('Lined up by distance, with a time gap chart', async () => {
    await expect(compare.alignDistance).toBeChecked()
    await expect(compare.traces).toHaveAttribute(
      'aria-label',
      'Power, Heart rate, Cadence, Speed, Altitude of each ride, lined up by distance',
    )
    await expect(compare.gapChart).toBeVisible()
    await expect(compare.curves).toBeVisible()
  })

  await test.step('Zoom in on the charts and back out', async () => {
    await compare.zoom.zoomIn(compare.traces)
    await expect(compare.zoom.showWholeRide).toBeEnabled()
    await compare.zoom.showWholeRide.click()
    await expect(compare.zoom.showWholeRide, {
      message: 'Once the whole ride shows there should be nothing to reset',
    }).toBeDisabled()
  })

  await test.step('The picks are still there back in the library', async () => {
    await compare.header.libraryLink.click()
    await expect(library.pick(EXPORT_A.name)).toBeChecked()
    await expect(library.pick(EXPORT_B.name)).toBeChecked()
  })
})

test('two to four rides compare; picks are kept while filtering, until cleared', async ({
  page,
}) => {
  const library = new LibraryPage(page)

  await test.step('Pick four rides', async () => {
    await library.goto()
    for (const ride of [ZWIFT, INTERVALS, EXPORT_A, EXPORT_B]) await library.pick(ride.name).check()
    await expect(library.compareButton).toHaveText('Compare (4)')
    await expect(library.selectionStatus).toHaveText(
      `Selected: ${[ZWIFT, INTERVALS, EXPORT_A, EXPORT_B].map((r) => r.name).join(', ')}.`,
    )
  })

  await test.step('A fifth ride can be selected (to edit), but not compared', async () => {
    await library.pick(HR_ONLY.name).check()
    await expect(library.selectionStatus).toHaveText('5 rides selected. Compare takes 2 to 4.')
    await expect(library.compareButton, {
      message: 'Compare should be off with more than 4 rides selected',
    }).toBeDisabled()
    await expect(library.editButton).toHaveText('Edit 5 rides')
    await library.pick(HR_ONLY.name).uncheck()
    await expect(library.compareButton).toBeEnabled()
  })

  await test.step('Picks stay when the list is filtered', async () => {
    await library.source.selectOption('zwift')
    await expect(library.rows).toHaveCount(1)
    await expect(library.pick(ZWIFT.name)).toBeChecked()
    await expect(library.compareButton).toHaveText('Compare (4)')
  })

  await test.step('Clear the selection', async () => {
    await library.clearSelection.click()
    await expect(library.pick(ZWIFT.name)).not.toBeChecked()
    await expect(library.compareButton).toHaveText('Compare (0)')
    await expect(library.clearSelection, {
      message: 'Clear selection should go once nothing is picked',
    }).toBeHidden()
  })
})

test('line up by time, change smoothing and remove rides', async ({ page, request }) => {
  const compare = new ComparePage(page)
  const testData = new TestData(request)

  await test.step('Compare the Zwift ride, the interval ride and an export', async () => {
    await compare.goto([
      await testData.rideId(ZWIFT.file),
      await testData.rideId(INTERVALS.file),
      await testData.rideId(EXPORT_A.file),
    ])
    await expect(compare.rides).toHaveCount(3)
    await expect(compare.smoothing).toHaveValue('10')
  })

  await test.step('Line up by time', async () => {
    await compare.alignTime.check()
    await expect(page).toHaveURL(/align=time/)
    await expect(compare.alignTime).toBeChecked()
    await expect(compare.traces).toHaveAttribute('aria-label', /lined up by time$/)
    await expect(compare.gapChart, {
      message: 'The time gap needs the rides lined up by distance',
    }).toBeHidden()
  })

  await test.step('Turn smoothing off', async () => {
    await compare.smoothing.selectOption('Off')
    await expect(page).toHaveURL(/smooth=0/)
    await expect(compare.alignTime, {
      message: 'Changing smoothing should keep the rides lined up by time',
    }).toBeChecked()
  })

  await test.step('Remove a ride', async () => {
    await compare.remove(INTERVALS.name).click()
    await expect(compare.rides).toHaveCount(2)
    await expect(compare.columnHeads()).toHaveText([ZWIFT.name, EXPORT_A.name])
  })

  await test.step('Removing down to one ride asks for more', async () => {
    await compare.remove(EXPORT_A.name).click()
    await expect(compare.empty).toContainText('Pick at least 2 rides to compare')
  })
})

test('compare from a ride’s similar rides', async ({ page, request }) => {
  const ride = new RidePage(page)
  const compare = new ComparePage(page)
  const intervals = await new TestData(request).rideId(INTERVALS.file)

  await test.step('Open the interval ride', async () => {
    await ride.goto(intervals)
    await expect(ride.similar.routeTable).toBeVisible()
  })

  await test.step('Compare it with one ride on the same route', async () => {
    await ride.similar.compareWith(EXPORT_B.name).click()
    await expect(compare.columnHeads()).toHaveText([INTERVALS.name, EXPORT_B.name])
  })

  await test.step('Compare it with its 3 closest rides', async () => {
    await ride.goto(intervals)
    await ride.similar.compareClosest(3).click()
    await expect(compare.rides).toHaveCount(4)
    await expect(compare.columnHeads().first(), {
      message: 'The ride itself should come first, as the one gaps are measured against',
    }).toHaveText(INTERVALS.name)
    await expect(compare.gapChart).toBeVisible()
  })
})
