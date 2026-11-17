import { test, expect } from '@playwright/test'
import { RidePage } from '../../pageObjects/ridePage'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Read-only: the interval ride's Ride Stats charts are switched and zoomed, nothing saved.
const { INTERVALS } = RIDES

test('ride stats switch between time and distance', async ({ page, request }) => {
  const ride = new RidePage(page)

  await test.step('Open the interval ride', async () => {
    await ride.goto(await new TestData(request).rideId(INTERVALS.file))
    await expect(ride.statsHeading).toBeVisible()
  })

  await test.step('The charts start over time', async () => {
    await expect(ride.overTime).toBeChecked()
    await expect(ride.traceChart).toHaveAttribute('aria-label', /over the ride, by time$/)
  })

  await test.step('Switch to distance', async () => {
    await ride.overDistance.check()
    await expect(ride.traceChart).toHaveAttribute(
      'aria-label',
      'Power, Heart rate, Cadence, Speed, Altitude over the ride, by distance',
    )
  })

  await test.step('And back to time', async () => {
    await ride.overTime.check()
    await expect(ride.traceChart).toHaveAttribute('aria-label', /by time$/)
  })
})

test('a zoomed-in chart goes back to the whole ride', async ({ page, request }) => {
  const ride = new RidePage(page)
  const { zoom } = ride

  await test.step('Open the interval ride', async () => {
    await ride.goto(await new TestData(request).rideId(INTERVALS.file))
    await expect(ride.traceChart).toBeVisible()
  })

  await test.step('The zoom bar is labelled, with nothing to reset yet', async () => {
    await expect(zoom.hint).toBeVisible()
    await expect(zoom.showWholeRide, {
      message: 'Show whole ride should wait until the chart is zoomed in',
    }).toBeDisabled()
  })

  await test.step('Zoom in', async () => {
    await zoom.zoomIn(ride.traceChart)
    await expect(zoom.showWholeRide).toBeEnabled()
  })

  await test.step('Show the whole ride again', async () => {
    await zoom.showWholeRide.click()
    await expect(zoom.showWholeRide, {
      message: 'Once the whole ride shows there should be nothing to reset',
    }).toBeDisabled()
  })
})
