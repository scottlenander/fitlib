import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'

// The Quit button, as the desktop launcher's server shows it (the e2e server allows quitting).
// Pressing the dialog's Quit would stop the server every spec shares, so these tests stop at
// the dialog; the API tests check that quitting stops a real server.

test('Quit asks first, and Cancel keeps fitlib running', async ({ page }) => {
  const library = new LibraryPage(page)
  const { header } = library

  await test.step('Open the library: Quit is in the header', async () => {
    await library.goto()
    await expect(header.quit).toHaveText('Quit')
  })

  await test.step('Quit asks first, with Cancel focused', async () => {
    await header.quit.click()
    await expect(header.quitDialog).toBeVisible()
    await expect(header.quitDialog).toContainText('stops importing from your watched folders')
    await expect(header.quitCancel, {
      message: 'Cancel should have the focus, so Enter never quits by accident',
    }).toBeFocused()
    await expect(header.quitConfirm).toBeEnabled()
  })

  await test.step('Cancel: the dialog closes and the library still loads', async () => {
    await header.quitCancel.click()
    await expect(header.quitDialog).toBeHidden()
    await page.reload()
    await expect(library.rows.first()).toBeVisible()
  })

  await test.step('Escape cancels too', async () => {
    await header.quit.click()
    await expect(header.quitDialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(header.quitDialog).toBeHidden()
    await expect(header.quit, { message: 'fitlib should still be running' }).toBeVisible()
  })
})
