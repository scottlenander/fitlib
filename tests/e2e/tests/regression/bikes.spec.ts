import { test, expect } from '@playwright/test'
import { BikesPage } from '../../pageObjects/bikesPage'
import { RidePage } from '../../pageObjects/ridePage'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Bikes can't be deleted, so each run adds its own.
const RUN = Date.now().toString(36)
// The only ride the "indoor" default affects; claimed in libs/constants.ts, as is the slot.
const INDOOR_RIDE = RIDES.INDOOR
const INDOOR = 'Indoor (not Zwift)'

test('adding, renaming, retiring and bringing back a bike', async ({ page }) => {
  const bikes = new BikesPage(page)
  const name = `Tarmac ${RUN}`
  const renamed = `Tarmac SL7 ${RUN}`

  await test.step('Add a road bike', async () => {
    await bikes.goto()
    await bikes.addBike(name, 'Road')
    await expect(bikes.addNotice).toHaveText(`Added ${name}.`)
    await expect(bikes.row(name)).toContainText('Road')
  })

  await test.step('The same name again, in another case, is refused', async () => {
    await bikes.addBike(name.toLowerCase())
    await expect(bikes.addError).toHaveText(
      `There is already a bike called '${name.toLowerCase()}'`,
    )
  })

  await test.step('Rename it and change its kind', async () => {
    await bikes.editButton(name).click()
    const form = bikes.editForm(name)
    await form.getByLabel('Name').fill(renamed)
    await form.getByLabel('Kind').selectOption({ label: 'Gravel' })
    await form.getByRole('button', { name: 'Save' }).click()
    await expect(bikes.row(renamed)).toContainText('Gravel')
    await expect(bikes.row(name), { message: 'The old name should be gone' }).toHaveCount(0)
  })

  await test.step('Retire it: hidden until retired bikes are shown', async () => {
    await bikes.retireButton(renamed).click()
    await expect(bikes.row(renamed), { message: 'Retired bikes are hidden' }).toHaveCount(0)
    await bikes.showRetired.check()
    await expect(bikes.row(renamed)).toContainText('(retired)')
  })

  await test.step('Bring it back', async () => {
    await bikes.bringBackButton(renamed).click()
    await expect(bikes.retireButton(renamed)).toBeVisible()
    await expect(bikes.row(renamed)).not.toContainText('(retired)')
  })
})

test('default bikes, and applying them to existing rides', async ({ page, request }) => {
  const bikes = new BikesPage(page)
  const ride = new RidePage(page)
  const trainer = `Trainer bike ${RUN}`

  await test.step('Add a bike for indoor rides', async () => {
    await bikes.goto()
    await bikes.addBike(trainer, 'Trainer')
    await expect(bikes.addNotice).toHaveText(`Added ${trainer}.`)
  })

  await test.step('Make it the indoor default from 2000', async () => {
    // Replaces an earlier run's entry on the same date.
    await bikes.setDefault(INDOOR, '2000-01-01', trainer)
    await expect(bikes.defaultRow(INDOOR, '2000-01-01')).toContainText(trainer)
  })

  await test.step('Add an entry with no bike, then remove it', async () => {
    await bikes.setDefault(INDOOR, '2030-01-01', 'No bike')
    await expect(bikes.defaultRow(INDOOR, '2030-01-01')).toContainText('No bike')
    await bikes.removeDefault(INDOOR, '2030-01-01')
  })

  await test.step('Preview what applying the defaults would change', async () => {
    await bikes.previewButton.click()
    await expect(bikes.backfillResult).toContainText('Would change 1 ride:')
    await expect(bikes.backfillResult).toContainText(`${trainer}: 1 ride`)
  })

  await test.step('Apply them', async () => {
    await bikes.applyButton.click()
    await expect(bikes.backfillResult).toContainText('Changed 1 ride:')
  })

  await test.step('The indoor ride has the bike, marked as a default', async () => {
    await ride.goto(await new TestData(request).rideId(INDOOR_RIDE.file))
    await expect(ride.details.value('Bike')).toHaveText(`${trainer} (default)`)
  })

  await test.step('Applying again changes nothing', async () => {
    await bikes.goto()
    await bikes.previewButton.click()
    await expect(bikes.backfillResult).toHaveText('Every ride already has its default bike.')
  })
})
