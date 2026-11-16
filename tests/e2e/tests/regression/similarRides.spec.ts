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
