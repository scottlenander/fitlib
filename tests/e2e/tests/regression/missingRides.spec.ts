import { test, expect, type Page } from '@playwright/test'
import { ComparePage } from '../../pageObjects/comparePage'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Read-only: two rides, and an id no ride has, standing for a ride deleted since (in another
// tab or from the command line). Nothing is changed.
const RIDE = RIDES.INTERVALS
const OTHER = RIDES.HR_ONLY
const GONE = { id: '00000000-0000-4000-8000-0000000000aa', name: 'A ride deleted since' }

// Puts rides in the library's selection, as if ticked earlier in this tab.
async function selectStored(page: Page, picked: { id: string; name: string }[]) {
  await page.goto('/')
  await page.evaluate(
    (value) => sessionStorage.setItem('fitlib.selection', value),
    JSON.stringify(picked),
  )
}

test('a compare link with a ride that is gone leaves it out', async ({ page, request }) => {
  const compare = new ComparePage(page)
  const testData = new TestData(request)
  const ids = [await testData.rideId(RIDE.file), GONE.id, await testData.rideId(OTHER.file)]

  await test.step('Open the link', async () => {
    await page.goto(`/compare?ids=${ids.join(',')}`)
  })

  await test.step('The other two are compared, and the page says one was left out', async () => {
    await expect(compare.rides).toHaveCount(2)
    await expect(compare.leftOut).toHaveText('Left out 1 ride that is no longer in the library.')
    await expect(compare.error, {
      message: 'No error should show once the ride is left out',
    }).toBeHidden()
    expect(page.url(), { message: 'The link should no longer name the ride' }).not.toContain(
      GONE.id,
    )
  })

  await test.step('With only one ride left, the page asks for more', async () => {
    await page.goto(`/compare?ids=${ids[0]},${GONE.id}`)
    await expect(compare.empty).toContainText('Pick at least 2 rides to compare')
    await expect(compare.leftOut).toHaveText('Left out 1 ride that is no longer in the library.')
  })
})

test('a selected ride that is gone is unselected when editing or deleting', async ({
  page,
  request,
}) => {
  const library = new LibraryPage(page)
  const form = library.bulkEdit
  const rideId = await new TestData(request).rideId(RIDE.file)
  const missing =
    '1 selected ride is no longer in the library and was unselected. Nothing was changed: try again.'

  await test.step('Start with the ride and a gone one selected', async () => {
    await selectStored(page, [{ id: rideId, name: RIDE.name }, GONE])
    await library.goto({ since: RIDE.date, until: RIDE.date })
    await expect(library.editButton).toHaveText('Edit 2 rides')
  })

  await test.step('Apply an effort: the gone ride is unselected, nothing changed', async () => {
    await library.editButton.click()
    await form.effort.selectOption('5')
    await form.apply.click()
    await expect(library.missingNotice).toHaveText(missing)
    await expect(library.editButton).toHaveText('Edit 1 ride')
    const ride = (await (await request.get(`/api/rides/${rideId}`)).json()) as {
      meta: { rpe: number | null }
    }
    expect(ride.meta.rpe, {
      message: 'The ride should keep no effort, as nothing was changed',
    }).toBeNull()
  })

  await test.step('Delete a selection holding only a gone ride: unselected, nothing deleted', async () => {
    await selectStored(page, [GONE])
    await library.goto({ since: RIDE.date, until: RIDE.date })
    await library.deleteButton.click()
    await library.confirmDelete.confirm.click()
    await expect(library.confirmDelete.root).toBeHidden()
    await expect(library.missingNotice).toHaveText(missing)
    await expect(library.deleteButton, { message: 'Nothing should be selected now' }).toBeHidden()
    await expect(library.row(RIDE.name)).toBeVisible()
  })
})
