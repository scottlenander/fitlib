import { test, expect, type Page } from '@playwright/test'
import { ComparePage } from '../../pageObjects/comparePage'
import { RidePage } from '../../pageObjects/ridePage'
import { SettingsPage } from '../../pageObjects/settingsPage'
import { expectNoViolations } from '../../libs/accessibility'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Read-only: two outdoor rides on the Nord loop, the Zwift ride (Watopia) and the indoor ride
// (no positions).
const OUTDOOR = RIDES.INTERVALS
const OTHER_OUTDOOR = RIDES.HR_ONLY
const ZWIFT = RIDES.ZWIFT
const INDOOR = RIDES.INDOOR
// OpenStreetMap's map images: answered by the test, never fetched.
const TILES = 'https://tile.openstreetmap.org/**'
// A 1x1 transparent PNG.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
  'base64',
)

// Counts requests for map images, answering each with a blank image.
async function countTiles(page: Page): Promise<{ count: number }> {
  const tiles = { count: 0 }
  await page.route(TILES, (route) => {
    tiles.count += 1
    return route.fulfill({ contentType: 'image/png', body: PNG })
  })
  return tiles
}

test("an outdoor ride's route, on a plain background, follows Ride Stats", async ({
  page,
  request,
}) => {
  const ride = new RidePage(page)
  const tiles = await countTiles(page)
  const rideId = await new TestData(request).rideId(OUTDOOR.file)

  await test.step('Open the ride: its route on a plain background', async () => {
    await ride.goto(rideId)
    await expect(ride.map.map).toHaveAttribute('data-routes', '1')
    await expect(ride.map.map).toHaveAccessibleName(
      /^Route map: 19\.9 mi, starts and finishes .+ apart\./,
    )
    await expect(ride.map.map).toHaveAttribute('data-street-map', 'off')
    await expect(ride.map.note).toContainText('Drawn without a street map')
    await expect(ride.map.settingsLink).toBeVisible()
  })

  await test.step('Pointing at Ride Stats puts a dot on the route', async () => {
    await expect(ride.map.map).toHaveAttribute('data-cursor', 'off')
    await ride.traceChart.scrollIntoViewIfNeeded()
    const box = await ride.traceChart.boundingBox()
    expect(box, { message: 'Ride Stats should be drawn' }).not.toBeNull()
    // Inside the top chart (power), where Ride Stats shows a moment.
    await page.mouse.move(box!.x + box!.width * 0.4, box!.y + 80)
    await expect(ride.map.map).toHaveAttribute('data-cursor', 'on')
    await page.mouse.move(0, 0)
    await expect(ride.map.map, {
      message: 'The dot should go when the pointer leaves the charts',
    }).toHaveAttribute('data-cursor', 'off')
  })

  await test.step('Zooming Ride Stats highlights that stretch; Show whole ride clears it', async () => {
    await expect(ride.map.map).toHaveAttribute('data-span', 'off')
    await ride.zoom.zoomIn(ride.traceChart)
    await expect(ride.map.map).toHaveAttribute('data-span', 'on')
    await ride.zoom.showWholeRide.click()
    await expect(ride.map.map).toHaveAttribute('data-span', 'off')
  })

  await test.step('Nothing was loaded from OpenStreetMap', () => {
    expect(tiles.count, { message: 'No map images should load with the street map off' }).toBe(0)
  })

  await test.step('No accessibility problems, in light and dark', async () => {
    await expectNoViolations(page)
    await page.emulateMedia({ colorScheme: 'dark' })
    await page.reload()
    await expect(ride.map.map).toHaveAttribute('data-routes', '1')
    await expectNoViolations(page)
  })
})

test('the street map, once turned on, goes under outdoor routes but not Zwift ones', async ({
  page,
  request,
}) => {
  const ride = new RidePage(page)
  const settings = new SettingsPage(page)
  const tiles = await countTiles(page)
  const testData = new TestData(request)

  await test.step('Turn on the street map in Settings', async () => {
    await settings.goto()
    await expect(settings.streetMap).toHaveAttribute('aria-checked', 'false')
    await settings.streetMap.click()
    await expect(settings.streetMap).toHaveAttribute('aria-checked', 'true')
  })

  await test.step('An outdoor ride: the street map under it, with its credit', async () => {
    await ride.goto(await testData.rideId(OUTDOOR.file))
    await expect(ride.map.map).toHaveAttribute('data-street-map', 'on')
    await expect(ride.map.credit).toBeVisible()
    await expect(ride.map.note).toHaveText('Street map © OpenStreetMap contributors.')
    await expect.poll(() => tiles.count, { message: 'Map images should load' }).toBeGreaterThan(0)
  })

  await test.step('A Zwift ride: plain background, as its positions are not real places', async () => {
    const before = tiles.count
    await ride.goto(await testData.rideId(ZWIFT.file))
    await expect(ride.map.map).toHaveAttribute('data-routes', '1')
    await expect(ride.map.map).toHaveAttribute('data-street-map', 'off')
    await expect(ride.map.note).toHaveText(
      "Zwift · Watopia: Zwift's positions aren't real places, so the route is drawn on a plain background.",
    )
    expect(tiles.count, { message: 'No map images should load for a Zwift ride' }).toBe(before)
  })

  await test.step('Turn it off again: kept across a reload', async () => {
    await settings.goto()
    await settings.streetMap.click()
    await page.reload()
    await expect(settings.streetMap).toHaveAttribute('aria-checked', 'false')
  })
})

test('a ride without positions has no map', async ({ page, request }) => {
  const ride = new RidePage(page)

  await test.step('Open the indoor ride', async () => {
    await ride.goto(await new TestData(request).rideId(INDOOR.file))
    await expect(ride.heading).toHaveText(INDOOR.name)
    await expect(ride.traceChart).toBeVisible()
    await expect(ride.map.heading, {
      message: 'An indoor ride without GPS should have no map section',
    }).toBeHidden()
  })
})

test('compared rides share a map when they are in the same place', async ({ page, request }) => {
  const compare = new ComparePage(page)
  const testData = new TestData(request)
  const ids = [
    await testData.rideId(OUTDOOR.file),
    await testData.rideId(OTHER_OUTDOOR.file),
    await testData.rideId(ZWIFT.file),
    await testData.rideId(INDOOR.file),
  ]

  await test.step('Compare two outdoor rides, the Zwift ride and the indoor ride', async () => {
    await page.goto(`/compare?ids=${ids.join(',')}`)
    await expect(compare.rides).toHaveCount(4)
  })

  await test.step('Both outdoor routes on the map; the others listed', async () => {
    await expect(compare.map.map).toHaveAttribute('data-routes', '2')
    await expect(compare.map.map).toHaveAccessibleName(
      new RegExp(`^Routes of ${OUTDOOR.name}, ${OTHER_OUTDOOR.name}\\.`),
    )
    await expect(compare.map.note).toHaveText(
      `Not on this map (somewhere else): ${ZWIFT.name}. No positions recorded: ${INDOOR.name}.`,
    )
    await expectNoViolations(page)
  })
})
