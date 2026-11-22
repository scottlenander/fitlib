import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { SettingsPage } from '../../pageObjects/settingsPage'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Changes the default time zone (owned by this spec), which moves only the NO_TIME_ZONE ride:
// a Wahoo ride with no local time and an undated name, starting 02:00 UTC on 11 Aug 2025.
// Both tests change the same setting, so they run one after the other.
const RIDE = RIDES.NO_TIME_ZONE
// Its name while no default time zone is set.
const RIDE_UTC_NAME = 'Ride 2025-08-11 02:00 UTC'

test.describe.configure({ mode: 'serial' })

test('the default time zone dates rides that carry none', async ({ page, request }) => {
  const settings = new SettingsPage(page)
  const ride = new RidePage(page)
  const library = new LibraryPage(page)
  const testData = new TestData(request)
  const rideId = await testData.rideId(RIDE.file)

  await test.step('Start with no default time zone', async () => {
    await testData.clearTimeZone()
  })

  await test.step('The ride starts at 02:00 UTC on 11 Aug', async () => {
    await ride.goto(rideId)
    await expect(ride.heading).toHaveText('Ride 2025-08-11 02:00 UTC')
    await expect(ride.subtitle).toContainText('Mon 11 Aug 2025, 02:00 UTC')
    await expect(ride.timeZoneNote).toHaveText(
      "Shown in UTC: the file doesn't say where it was ridden. Set a default time zone in Settings.",
    )
  })

  await test.step('In the library, its date is marked as UTC', async () => {
    await library.goto({ since: '2025-08-11', until: '2025-08-11' })
    await expect(library.row(RIDE_UTC_NAME)).toContainText('2025-08-11 UTC')
  })

  await test.step('Choose New York as the default', async () => {
    await settings.goto()
    await expect(settings.timeZone).toHaveValue('')
    await settings.timeZone.selectOption('America/New_York')
    await settings.saveTimeZone.click()
    await expect(settings.timeZoneNotice).toHaveText('Saved: America/New York. 1 ride updated.')
  })

  await test.step('The ride is now the evening before, in New York time', async () => {
    await ride.goto(rideId)
    await expect(ride.heading).toHaveText('Ride 2025-08-10 22:00')
    await expect(ride.subtitle).toContainText('Sun 10 Aug 2025, 22:00 ·')
    await expect(ride.timeZoneNote).toHaveText(
      "Time zone: your default (America/New York), as the file doesn't say. Change it in Settings.",
    )
  })

  await test.step('The note leads to Settings', async () => {
    await ride.timeZoneNote.getByRole('link', { name: 'Settings' }).click()
    await expect(settings.heading).toBeVisible()
  })

  await test.step('Clear the default, and the ride is back in UTC', async () => {
    await settings.goto()
    await settings.timeZone.selectOption('')
    await settings.saveTimeZone.click()
    await expect(settings.timeZoneNotice).toHaveText('Saved: none (UTC). 1 ride updated.')
    await ride.goto(rideId)
    await expect(ride.subtitle).toContainText('Mon 11 Aug 2025, 02:00 UTC')
  })
})

test.describe('on a computer in Tokyo', () => {
  test.use({ timezoneId: 'Asia/Tokyo' })

  test("the computer's time zone can be chosen with one click", async ({ page, request }) => {
    const settings = new SettingsPage(page)
    const ride = new RidePage(page)
    const testData = new TestData(request)

    await test.step('Start with no default time zone', async () => {
      await testData.clearTimeZone()
      await settings.goto()
      await expect(settings.timeZone).toHaveValue('')
    })

    await test.step("Use this computer's time zone", async () => {
      await expect(settings.useComputersZone).toHaveText(
        "Use this computer's time zone (Asia/Tokyo)",
      )
      await settings.useComputersZone.click()
      await expect(settings.timeZone).toHaveValue('Asia/Tokyo')
      await settings.saveTimeZone.click()
      await expect(settings.timeZoneNotice).toHaveText('Saved: Asia/Tokyo. 1 ride updated.')
    })

    await test.step('The ride is at 11:00 Tokyo time', async () => {
      await ride.goto(await testData.rideId(RIDE.file))
      await expect(ride.subtitle).toContainText('Mon 11 Aug 2025, 11:00 ·')
    })

    await test.step('Leave no default time zone', async () => {
      await testData.clearTimeZone()
    })
  })
})
