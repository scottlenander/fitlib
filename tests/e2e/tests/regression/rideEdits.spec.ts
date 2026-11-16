import { test, expect } from '@playwright/test'
import { BikesPage } from '../../pageObjects/bikesPage'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Renamed, tagged, rated and given a bike; claimed in libs/constants.ts and reset first.
const RIDE = RIDES.SMART
// Bikes can't be deleted, so each run adds its own.
const BIKE = `Edit test bike ${Date.now().toString(36)}`
const NEW_NAME = 'Tempo along the canal'

// Both tests edit the same ride.
test.describe.configure({ mode: 'serial' })

test("editing a ride's details shows them on the ride and in the library", async ({
  page,
  request,
}) => {
  const ride = new RidePage(page)
  const library = new LibraryPage(page)
  const bikes = new BikesPage(page)
  let rideId = ''

  await test.step('Start with no edits, and a bike to choose', async () => {
    rideId = await new TestData(request).rideId(RIDE.file)
    await new TestData(request).resetMeta(rideId)
    await bikes.goto()
    await bikes.addBike(BIKE)
    await expect(bikes.addNotice).toHaveText(`Added ${BIKE}.`)
  })

  await test.step('Edit every detail and save', async () => {
    await ride.goto(rideId)
    await expect(ride.noDetails).toBeVisible()
    await ride.editButton.click()
    await ride.editName.fill(NEW_NAME)
    await ride.editEffort.selectOption({ label: '7/10' })
    await ride.editBike.selectOption({ label: BIKE })
    await ride.editTags.fill('Tempo, base , tempo')
    await ride.editNotes.fill('Windy on the way back.')
    await ride.saveButton.click()
    await expect(ride.saved).toHaveText('Saved.')
  })

  await test.step('The ride shows the new details', async () => {
    await expect(ride.heading).toHaveText(NEW_NAME)
    await expect(ride.details.value('Bike'), {
      message: 'A bike chosen by hand should not be marked as a default',
    }).toHaveText(BIKE)
    await expect(ride.details.value('Effort')).toHaveText('7/10')
    await expect(ride.details.value('Tags')).toHaveText('base, tempo')
    await expect(ride.notes).toHaveText('Windy on the way back.')
  })

  await test.step('Still there after a reload', async () => {
    await page.reload()
    await expect(ride.heading).toHaveText(NEW_NAME)
  })

  await test.step('The library finds it by name, tag, bike and effort', async () => {
    await library.goto()
    await library.searchFor('canal')
    await expect(library.rideNames()).toHaveText([NEW_NAME])
    await expect(library.row(NEW_NAME)).toContainText(BIKE)
    await expect(library.row(NEW_NAME)).toContainText('base, tempo')

    await library.clearFilters.click()
    await library.tag.selectOption('tempo')
    await expect(library.rideNames()).toHaveText([NEW_NAME])

    await library.clearFilters.click()
    await library.bike.selectOption({ label: BIKE })
    await expect(library.rideNames()).toHaveText([NEW_NAME])

    await library.clearFilters.click()
    await library.effortFrom.selectOption('7')
    await library.effortTo.selectOption('7')
    await expect(library.rideNames()).toHaveText([NEW_NAME])
  })
})

test('clearing details, a bad tag and cancelling an edit', async ({ page, request }) => {
  const ride = new RidePage(page)
  let rideId = ''

  await test.step('Start with an effort and tags', async () => {
    rideId = await new TestData(request).rideId(RIDE.file)
    await new TestData(request).resetMeta(rideId)
    await ride.goto(rideId)
    await ride.editButton.click()
    await ride.editEffort.selectOption({ label: '5/10' })
    await ride.editTags.fill('recovery')
    await ride.saveButton.click()
    await expect(ride.details.value('Effort')).toHaveText('5/10')
  })

  await test.step('Clear the effort and tags', async () => {
    await ride.editButton.click()
    await ride.editEffort.selectOption({ label: 'Not set' })
    await ride.editTags.fill('')
    await ride.saveButton.click()
    await expect(ride.noDetails).toBeVisible()
  })

  await test.step('A tag that is too long is refused and nothing is saved', async () => {
    await ride.editButton.click()
    await ride.editEffort.selectOption({ label: '9/10' })
    await ride.editTags.fill('x'.repeat(41))
    await ride.saveButton.click()
    await expect(ride.editError).toContainText('Tags can be at most 40 characters')
    await ride.cancelButton.click()
    await expect(ride.noDetails, { message: 'The refused edit should not be saved' }).toBeVisible()
  })

  await test.step('Cancel throws away a change', async () => {
    await ride.editButton.click()
    await ride.editName.fill('Not saved')
    await ride.cancelButton.click()
    await expect(ride.heading).toHaveText(RIDE.name)
    await page.reload()
    await expect(ride.heading).toHaveText(RIDE.name)
  })
})
