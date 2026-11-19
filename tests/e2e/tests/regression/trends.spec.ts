import { test, expect } from '@playwright/test'
import { RidePage } from '../../pageObjects/ridePage'
import { TrendsPage } from '../../pageObjects/trendsPage'
import { RIDES } from '../../libs/constants'

// Read-only. 18 to 31 Aug 2025 holds the indoor ride (19 Aug, 30 min at 210 W, no heart
// rate) and the two export rides (23 and 24 Aug); no other spec changes anything that counts
// there. Earlier August rides are changed elsewhere (the 9 Aug ride is re-imported, the 11 Aug
// ride moves with the time zone), so fitness and fatigue, which build up from the first ride,
// are only checked where they don't depend on those. Best efforts are compared with the
// interval ride (5 Aug: best 20 minutes 228 W, so an estimated FTP of 217 W).
const RANGE = { since: '2025-08-18', until: '2025-08-31' }
const { INDOOR, EXPORT_A, INTERVALS } = RIDES

// Today on this computer, as the page works it out.
function today(): Date {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate())
}

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

test('volume, FTP and efficiency for a fixed range, with their tables', async ({ page }) => {
  const trends = new TrendsPage(page)
  const ride = new RidePage(page)

  await test.step('Open 18 to 31 Aug 2025', async () => {
    await trends.goto(RANGE)
    await expect(trends.preset('Custom')).toBeChecked()
    await expect(trends.from).toHaveValue(RANGE.since)
    await expect(trends.rangeText).toContainText('Mon 18 Aug 2025 to Sun 31 Aug 2025')
    await expect(trends.summary.value('Estimated FTP')).toHaveText('217 W')
    await expect(trends.summary.value('FTP'), {
      message: 'No FTP is set in the fixture library',
    }).toHaveText('–')
  })

  await test.step('Volume by week, as a table', async () => {
    await expect(trends.volumeChart).toBeVisible()
    await trends.showTable(trends.volume).click()
    await expect(trends.row(trends.volumeTable, 'Week of 18 Aug 2025')).toContainText(
      ['3', '1:15:00', '25.2 mi', '538 ft', '833 kJ', '92'].join(''),
    )
    await expect(trends.row(trends.volumeTable, 'Week of 25 Aug 2025'), {
      message: 'An empty week should be listed with zeros',
    }).toContainText('00:000.0 mi')
  })

  await test.step('Show distance instead of time', async () => {
    await trends.volumeMetric.selectOption({ label: 'Distance' })
    await expect(page).toHaveURL(/metric=distance/)
    await expect(trends.volumeChart).toHaveAttribute('aria-label', 'Volume by week: mi')
  })

  await test.step('Group by month', async () => {
    await trends.groupBy.selectOption({ label: 'Month' })
    await expect(page).toHaveURL(/period=month/)
    // The month is widened back to 1 Aug, which holds rides other specs change: no counts.
    await expect(trends.row(trends.volumeTable, 'Aug 2025')).toBeVisible()
    await expect(trends.volumeTable).toHaveAccessibleName('Volume by month')
    await trends.groupBy.selectOption({ label: 'Week' })
  })

  await test.step('FTP at the end of each week', async () => {
    await expect(trends.ftpChart).toBeVisible()
    await trends.showTable(trends.ftp).click()
    for (const sunday of ['Sun 24 Aug 2025', 'Sun 31 Aug 2025']) {
      await expect(trends.row(trends.ftpTable, sunday)).toContainText('–217 W')
    }
  })

  await test.step('Efficiency of the export rides; the indoor ride has no heart rate', async () => {
    await expect(trends.efficiencyChart).toBeVisible()
    await trends.showTable(trends.efficiency).click()
    await expect(trends.efficiencyTable.getByRole('row')).toHaveCount(3) // a header and 2 rides
    await expect(trends.row(trends.efficiencyTable, 'Sat 23 Aug 2025')).toContainText(
      '160 W130 bpm1.23',
    )
    await expect(trends.row(trends.efficiencyTable, 'Sun 24 Aug 2025')).toContainText(
      '175 W134 bpm1.31',
    )
  })

  await test.step('Open a ride from the efficiency table', async () => {
    await trends.efficiencyTable.getByRole('link', { name: 'Sat 23 Aug 2025' }).click()
    await expect(ride.heading).toHaveText(EXPORT_A.name)
  })
})

test('fitness, and best efforts against the past year and the period before', async ({ page }) => {
  const trends = new TrendsPage(page)
  const ride = new RidePage(page)

  await test.step('Open 18 to 31 Aug 2025', async () => {
    await trends.goto(RANGE)
    await expect(trends.fitnessChart).toBeVisible()
  })

  await test.step('Fitness each Sunday, with the TSS ridden that day', async () => {
    await expect(trends.withoutTss, {
      message: 'Every ride in the range has power, so all have TSS',
    }).toBeHidden()
    await trends.showTable(trends.fitness).click()
    await expect(trends.fitnessTable.getByRole('row')).toHaveCount(3) // a header and 2 Sundays
    // The 24 Aug export ride: 25 min at 175 W against the estimated 217 W.
    await expect(
      trends.row(trends.fitnessTable, 'Sun 24 Aug 2025').getByRole('cell').first(),
    ).toHaveText('27')
  })

  await test.step('Best power against the past year', async () => {
    await expect(trends.bestChart).toBeVisible()
    await trends.showTable(trends.best).click()
    await expect(trends.bestTable).toHaveAccessibleName(
      'Best efforts: This range against Past year (01 Sep 2024 to 31 Aug 2025)',
    )
    // The indoor ride's 210 W against the interval ride's 228 W.
    await expect(trends.row(trends.bestTable, '20 min')).toContainText('210 W228 W-7.9 %')
    await expect(trends.row(trends.bestTable, '1 h'), {
      message: 'No ride in the range lasted an hour; the Zwift ride did in the past year',
    }).toContainText('–200 W–')
  })

  await test.step('Against the two weeks before', async () => {
    await trends.bestAgainst.selectOption({ label: 'Previous period' })
    await expect(page).toHaveURL(/against=previous/)
    await expect(trends.bestTable).toHaveAccessibleName(
      'Best efforts: This range against Previous period (04 Aug 2025 to 17 Aug 2025)',
    )
    await expect(trends.row(trends.bestTable, '20 min')).toContainText('210 W228 W')
  })

  await test.step('Heart rate instead of power', async () => {
    await trends.bestKind.selectOption({ label: 'Heart rate' })
    await expect(page).toHaveURL(/curve=hr/)
    await expect(trends.row(trends.bestTable, '20 min')).toContainText('134 bpm')
  })

  await test.step('Open the ride behind a best', async () => {
    await trends.bestKind.selectOption({ label: 'Power' })
    await trends.row(trends.bestTable, '20 min').getByRole('link', { name: '210 W' }).click()
    await expect(ride.heading).toHaveText(INDOOR.name)
  })

  await test.step('Back on the trends page, the choices are kept', async () => {
    await page.goBack()
    await expect(trends.bestAgainst).toHaveValue('previous')
    await expect(trends.from).toHaveValue(RANGE.since)
    // The interval ride's best is in the previous period: it opens from there too.
    await trends.showTable(trends.best).click()
    await trends.row(trends.bestTable, '20 min').getByRole('link', { name: '228 W' }).click()
    await expect(ride.heading).toHaveText(INTERVALS.name)
  })
})

test('a preset range ends today and is kept in the URL; a backwards range is refused', async ({
  page,
}) => {
  const trends = new TrendsPage(page)
  const yearAgo = today()
  yearAgo.setDate(yearAgo.getDate() - 364)

  await test.step('Open trends from the header: the last 3 months', async () => {
    await page.goto('/')
    await trends.header.trendsLink.click()
    await expect(trends.heading).toBeVisible()
    await expect(trends.preset('3 months')).toBeChecked()
    await expect(trends.to).toHaveValue(iso(today()))
  })

  await test.step('Choose 1 year', async () => {
    await trends.preset('1 year').check()
    await expect(page).toHaveURL(/range=1y/)
    await expect(trends.from).toHaveValue(iso(yearAgo))
  })

  await test.step('Still 1 year after a reload', async () => {
    await page.reload()
    await expect(trends.preset('1 year')).toBeChecked()
  })

  await test.step('A first day after the last is refused', async () => {
    await trends.goto({ since: '2025-09-30', until: '2025-08-31' })
    await expect(trends.error).toHaveText('The first day must be on or before the last day.')
    await expect(trends.fitness, {
      message: 'Nothing should be shown for a range that ends before it starts',
    }).toBeHidden()
  })
})
