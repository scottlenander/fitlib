import path from 'node:path'
import { test, expect } from '@playwright/test'
import { ImportPage } from '../../pageObjects/importPage'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { expectNoViolations } from '../../libs/accessibility'
import { EXTRA, EXTRA_DIR } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// An extra ride (8 Aug, a day with no other ride), imported at the start of each test, then
// deleted through the app; the first test brings it back through the Import page. The
// library is narrowed to its day.
const RIDE = EXTRA.DELETE
const DAY = { since: '2025-08-08', until: '2025-08-08' }
// Both tests delete the same ride, so they run one at a time.
test.describe.configure({ mode: 'serial' })

test('delete a ride from its page, then import it again on purpose', async ({ page, request }) => {
  const ride = new RidePage(page)
  const library = new LibraryPage(page)
  const importPage = new ImportPage(page)
  const dialog = ride.confirmDelete
  let rideId = ''

  await test.step('Start with the ride in the library', async () => {
    const testData = new TestData(request)
    rideId =
      (await testData.findRideId(RIDE.file)) ??
      (await testData.importFile(path.join(EXTRA_DIR, RIDE.file)))
  })

  await test.step('Ask to delete it, then cancel', async () => {
    await ride.goto(rideId)
    await expect(ride.heading).toHaveText(RIDE.name)
    await ride.deleteButton.click()
    await expect(dialog.heading).toHaveText('Delete this ride?')
    await expect(dialog.rides).toHaveText([RIDE.name])
    await expect(dialog.cancel, {
      message: 'Cancel should have the focus, so Enter never deletes by accident',
    }).toBeFocused()
    await expectNoViolations(page)
    await dialog.cancel.click()
    await expect(dialog.root).toBeHidden()
    await expect(ride.heading).toHaveText(RIDE.name)
  })

  await test.step('Escape cancels too', async () => {
    await ride.deleteButton.click()
    await expect(dialog.root).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog.root).toBeHidden()
  })

  await test.step('Delete it: back in the library, which says so', async () => {
    await ride.deleteButton.click()
    await dialog.confirm.click()
    await expect(library.heading).toBeVisible()
    await expect(library.deletedNotice).toHaveText(`Deleted ${RIDE.name}.`)
    await library.goto(DAY)
    await expect(library.count).toHaveText('No rides found.')
  })

  await test.step('Its page is gone', async () => {
    await ride.goto(rideId)
    await expect(ride.heading).toHaveText('Ride not found')
  })

  await test.step('Importing its file again leaves it out', async () => {
    await importPage.goto()
    await importPage.fileInput.setInputFiles(path.join(EXTRA_DIR, RIDE.file))
    await importPage.importButton.click()
    await expect(importPage.summary).toHaveText(
      'Imported 0, already in library 0, skipped 0, failed 0, deleted before 1.',
    )
    await expect(importPage.deleted).toContainText(`${RIDE.file}: You deleted this ride on`)
  })

  await test.step('Import it anyway: it is back', async () => {
    await importPage.importAnyway.click()
    await expect(importPage.summary).toHaveText(
      'Imported 1, already in library 0, skipped 0, failed 0.',
    )
    await importPage.imported.getByRole('link', { name: RIDE.file }).click()
    await expect(ride.heading).toHaveText(RIDE.name)
  })
})

test('delete rides selected in the library', async ({ page, request }) => {
  const library = new LibraryPage(page)
  const dialog = library.confirmDelete

  await test.step('Start with the ride in the library', async () => {
    const testData = new TestData(request)
    if (!(await testData.findRideId(RIDE.file)))
      await testData.importFile(path.join(EXTRA_DIR, RIDE.file))
  })

  await test.step('Select it and ask to delete', async () => {
    await library.goto(DAY)
    await expect(library.rows).toHaveCount(1)
    await library.pick(RIDE.name).check()
    await library.deleteButton.click()
    await expect(dialog.heading).toHaveText('Delete this ride?')
    await expect(dialog.confirm).toHaveText('Delete 1 ride')
  })

  await test.step('Delete: gone, unselected, and the library says so', async () => {
    await dialog.confirm.click()
    await expect(dialog.root).toBeHidden()
    await expect(library.deletedNotice).toHaveText('Deleted 1 ride.')
    await expect(library.count).toHaveText('No rides found.')
    await expect(library.deleteButton, {
      message: 'The deleted ride should no longer be selected',
    }).toBeHidden()
  })
})
