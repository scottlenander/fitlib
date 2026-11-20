import path from 'node:path'
import { test, expect } from '@playwright/test'
import { BikesPage } from '../../pageObjects/bikesPage'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { expectNoViolations } from '../../libs/accessibility'
import { EXTRA, EXTRA_DIR } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Two extra rides (3 and 4 Aug), imported if they aren't in the library and cleared of
// earlier runs' edits, then edited together. The library is narrowed to those two days, which
// hold no other ride. Bikes can't be deleted, so each run adds its own.
const { BULK_1, BULK_2 } = EXTRA
const DAYS = { since: '2025-08-03', until: '2025-08-04' }
const RUN = Date.now().toString(36)
// Both tests edit the same two rides, so they run one at a time.
test.describe.configure({ mode: 'serial' })

// Tags no other spec uses.
const COBBLES = 'bulk-cobbles'
const WET = 'bulk-wet'

test('edit the effort, bike and tags of several rides at once', async ({ page, request }) => {
  const library = new LibraryPage(page)
  const bikes = new BikesPage(page)
  const form = library.bulkEdit
  const testData = new TestData(request)
  const bike = `Bulk gravel ${RUN}`

  await test.step('Start with both rides in the library, unedited', async () => {
    for (const ride of [BULK_1, BULK_2]) {
      const id = await testData.findRideId(ride.file)
      if (id) await testData.resetMeta(id)
      else await testData.importFile(path.join(EXTRA_DIR, ride.file))
    }
  })

  await test.step('Add a bike for them', async () => {
    await bikes.goto()
    await bikes.addBike(bike, 'Gravel')
    await expect(bikes.addNotice).toHaveText(`Added ${bike}.`)
  })

  await test.step('Select both rides with the page checkbox', async () => {
    await library.goto(DAYS)
    await expect(library.rows).toHaveCount(2)
    await library.selectPage.check()
    await expect(library.pick(BULK_1.name)).toBeChecked()
    await expect(library.selectionStatus).toHaveText(`Selected: ${BULK_2.name}, ${BULK_1.name}.`)
  })

  await test.step('Open the edit form: nothing to apply yet', async () => {
    await library.editButton.click()
    await expect(form.heading).toHaveText('Edit 2 rides')
    await expect(form.apply, {
      message: 'Apply should wait until something is chosen to change',
    }).toBeDisabled()
    await expectNoViolations(page)
  })

  await test.step('Set an effort, the bike and two tags on both', async () => {
    await form.effort.selectOption('6')
    await form.bike.selectOption({ label: bike })
    await form.addTags.fill(`${COBBLES}, ${WET}`)
    await form.apply.click()
    await expect(form.notice).toHaveText('Updated 2 rides.')
    for (const ride of [BULK_1, BULK_2]) {
      await expect(library.row(ride.name)).toContainText(bike)
      await expect(library.row(ride.name)).toContainText(`${COBBLES}, ${WET}`)
    }
    await expect(form.effort, {
      message: 'The form should be ready for the next change',
    }).toHaveValue('')
  })

  await test.step('Unselect one: the page checkbox is part-ticked', async () => {
    await library.pick(BULK_1.name).uncheck()
    await expect(library.selectPage).toBeChecked({ indeterminate: true })
    await expect(form.heading).toHaveText('Edit 1 ride')
  })

  await test.step('Take a tag off and clear the effort of the other', async () => {
    await form.effort.selectOption({ label: 'No effort' })
    await form.removeTags.fill(WET)
    await form.apply.click()
    await expect(form.notice).toHaveText('Updated 1 ride.')
    await expect(
      library.row(BULK_2.name).getByRole('cell', { name: COBBLES, exact: true }),
    ).toBeVisible()
    await expect(library.row(BULK_1.name), {
      message: 'The unselected ride should keep both tags',
    }).toContainText(`${COBBLES}, ${WET}`)
  })

  await test.step('The library filters find the edits', async () => {
    await library.effortFrom.selectOption('6')
    await expect(library.rows).toHaveCount(1)
    await expect(library.row(BULK_1.name)).toBeVisible()
    await library.effortFrom.selectOption('')
    await library.tag.selectOption(COBBLES)
    await expect(library.rows).toHaveCount(2)
  })

  await test.step('Close the form and clear the selection', async () => {
    await form.close.click()
    await expect(form.root, { message: 'Close should hide the form' }).toBeHidden()
    await library.clearSelection.click()
    await expect(library.editButton, {
      message: 'There is nothing to edit with nothing selected',
    }).toBeHidden()
  })
})

test('a bad tag is refused and no ride changes', async ({ page, request }) => {
  const library = new LibraryPage(page)
  const form = library.bulkEdit
  const testData = new TestData(request)

  await test.step('Start with both rides in the library, unedited', async () => {
    for (const ride of [BULK_1, BULK_2]) {
      const id = await testData.findRideId(ride.file)
      if (id) await testData.resetMeta(id)
      else await testData.importFile(path.join(EXTRA_DIR, ride.file))
    }
  })

  await test.step('Select both and add a tag that is too long, with an effort', async () => {
    await library.goto(DAYS)
    await library.selectPage.check()
    await library.editButton.click()
    await form.effort.selectOption('3')
    await form.addTags.fill('x'.repeat(41))
    await form.apply.click()
    await expect(form.error).toContainText('Tags can be at most 40 characters')
  })

  await test.step('Neither ride changed', async () => {
    await library.effortFrom.selectOption('3')
    await expect(library.count, {
      message: 'The effort should not be saved when a tag is refused',
    }).toHaveText('No rides found.')
  })
})
