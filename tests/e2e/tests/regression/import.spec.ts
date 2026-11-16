import { test, expect } from '@playwright/test'
import { ImportPage } from '../../pageObjects/importPage'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { RIDES, UPLOADS } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Deleted, then imported again through the page; claimed in libs/constants.ts.
const RIDE = RIDES.PAUSE

test('importing a new ride adds it to the library', async ({ page, request }) => {
  const importPage = new ImportPage(page)
  const ride = new RidePage(page)
  const library = new LibraryPage(page)

  await test.step('Start without the 9 Aug ride', async () => {
    const testData = new TestData(request)
    const id = await testData.findRideId(RIDE.file)
    // Missing only if an earlier run stopped after deleting it.
    if (id) await testData.deleteRide(id)
  })

  await test.step('Import its file', async () => {
    await importPage.goto()
    await importPage.importFixtures(RIDE.file)
    await expect(importPage.summary).toHaveText(
      'Imported 1, already in library 0, skipped 0, failed 0.',
    )
  })

  await test.step('Open the new ride from the results', async () => {
    await importPage.imported.getByRole('link', { name: RIDE.file }).click()
    await expect(ride.heading).toHaveText(RIDE.name)
  })

  await test.step('It is in the library', async () => {
    await library.goto({ since: RIDE.date, until: RIDE.date })
    await expect(library.rideNames()).toHaveText([RIDE.name])
  })
})

test('rides already imported, other activities and broken files are reported', async ({ page }) => {
  const importPage = new ImportPage(page)

  await test.step('Choose four files', async () => {
    await importPage.goto()
    await importPage.fileInput.setInputFiles(
      [UPLOADS.EXPORT_ZIP, UPLOADS.RUN, UPLOADS.OVERLAP, UPLOADS.CORRUPT].map((f) =>
        importPage.fixturePath(f),
      ),
    )
    await expect(importPage.chosen).toHaveText('4 files chosen')
  })

  await test.step('Import them', async () => {
    await importPage.importButton.click()
    await expect(importPage.summary).toHaveText(
      'Imported 0, already in library 2, skipped 2, failed 1.',
    )
  })

  await test.step('Each file is listed with why', async () => {
    await expect(importPage.duplicates).toContainText('garmin_export.zip:garmin_export_ride_a.fit')
    await expect(importPage.skipped).toContainText(`${UPLOADS.RUN}: not a ride (running)`)
    await expect(importPage.skipped).toContainText(`${UPLOADS.OVERLAP}: overlaps ride`)
    await expect(importPage.failed).toContainText(`${UPLOADS.CORRUPT}: not a readable FIT file`)
    await expect(importPage.imported, { message: 'Nothing new should be imported' }).toBeHidden()
  })
})
