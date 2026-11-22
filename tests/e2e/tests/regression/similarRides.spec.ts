import { test, expect } from '@playwright/test'
import { RidePage } from '../../pageObjects/ridePage'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Read-only. Every outdoor fixture ride laps the same loop. Checks only name rides no other
// spec changes (the 12 Aug ride is renamed and the 9 Aug ride re-imported elsewhere).
const { INTERVALS, ZWIFT, INDOOR, HR_ONLY, EXPORT_A, EXPORT_B } = RIDES

test('rides on the same route are listed, newest first, and open', async ({ page, request }) => {
  const ride = new RidePage(page)
  const { similar } = ride

  await test.step('Open the interval ride', async () => {
    await ride.goto(await new TestData(request).rideId(INTERVALS.file))
    await expect(similar.routeTab).toHaveAttribute('aria-selected', 'true')
  })

  await test.step('The other rides on the loop are the same route', async () => {
    await expect(similar.routeTable).toBeVisible()
    for (const other of [EXPORT_B, EXPORT_A, HR_ONLY]) {
      await expect(similar.row(other.name)).toContainText('100%')
      await expect(similar.row(other.name)).toContainText('Same')
    }
    await expect(similar.rows.first(), {
      message: 'The newest ride on the route should be first',
    }).toContainText(EXPORT_B.name)
    await expect(similar.rideLink(ZWIFT.name), {
      message: 'The Zwift ride is in Watopia, not on this loop',
    }).toHaveCount(0)
  })

  await test.step('Open one of them', async () => {
    await similar.rideLink(EXPORT_B.name).click()
    await expect(ride.heading).toHaveText(EXPORT_B.name)
  })
})

test('similar efforts, reached with the arrow keys', async ({ page, request }) => {
  const ride = new RidePage(page)
  const { similar } = ride

  await test.step('Open the interval ride', async () => {
    await ride.goto(await new TestData(request).rideId(INTERVALS.file))
    await expect(similar.routeTable).toBeVisible()
  })

  await test.step('Move to the Similar efforts tab with the right arrow', async () => {
    await similar.routeTab.focus()
    await page.keyboard.press('ArrowRight')
    await expect(similar.effortTab).toBeFocused()
    await expect(similar.effortTab).toHaveAttribute('aria-selected', 'true')
  })

  await test.step('The closest effort comes first', async () => {
    await expect(similar.effortTable).toBeVisible()
    await expect(similar.rows.first()).toContainText(ZWIFT.name)
    await expect(similar.rideLink(HR_ONLY.name), {
      message: 'A ride without power should not be compared with one with power',
    }).toHaveCount(0)
  })
})

test('rides with nothing on their route say why', async ({ page, request }) => {
  const ride = new RidePage(page)
  const testData = new TestData(request)

  await test.step('The indoor ride has no GPS', async () => {
    await ride.goto(await testData.rideId(INDOOR.file))
    await expect(ride.similar.empty).toHaveText(
      'This ride has no GPS positions, so it has no route to match.',
    )
  })

  await test.step('The Zwift ride is alone in Watopia', async () => {
    await ride.goto(await testData.rideId(ZWIFT.file))
    await expect(ride.similar.empty).toHaveText("No other rides share this ride's route.")
  })
})

test('progress on a route lists its rides oldest first, by speed', async ({ page, request }) => {
  const ride = new RidePage(page)
  const { progress } = ride
  const testData = new TestData(request)

  await test.step('Open the 23 Aug export ride, on the loop', async () => {
    await ride.goto(await testData.rideId(EXPORT_A.file))
    await expect(progress.chart).toHaveAttribute(
      'aria-label',
      'Avg speed of each ride on this route, by date',
    )
  })

  await test.step('Its table lists the loop, oldest first, this ride marked', async () => {
    await progress.showTable.click()
    await expect(progress.rows.first(), {
      message: 'The interval ride (5 Aug) is the oldest on the loop',
    }).toContainText(INTERVALS.name)
    await expect(progress.thisRide()).toContainText('2025-08-23')
    await expect(progress.row(EXPORT_B.name)).toContainText('19.8 mph')
    await expect(progress.rows.last()).toContainText(EXPORT_B.name)
  })

  // The heart-rate-only ride's threshold comes from the rides with power before it.
  await test.step('The ride without power has its TSS from heart rate, explained', async () => {
    await expect(progress.row(HR_ONLY.name)).toContainText(/\d+ HR\*/)
    await expect(
      progress.root.getByText('HR: TSS from heart rate, as the ride has no power.'),
    ).toBeVisible()
  })

  await test.step('Show power instead', async () => {
    await progress.metric.selectOption({ label: 'Avg power' })
    await expect(progress.chart).toHaveAttribute(
      'aria-label',
      'Avg power of each ride on this route, by date',
    )
  })

  await test.step('Open the oldest ride on the route', async () => {
    await progress.row(INTERVALS.name).getByRole('link').click()
    await expect(ride.heading).toHaveText(INTERVALS.name)
  })

  await test.step('A ride alone on its route has no progress section', async () => {
    await ride.goto(await testData.rideId(ZWIFT.file))
    await expect(ride.similar.empty).toBeVisible()
    await expect(progress.root, {
      message: 'The Zwift ride is the only one in Watopia',
    }).toBeHidden()
  })
})
