import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { SettingsPage } from '../../pageObjects/settingsPage'
import { RIDES } from '../../libs/constants'

// Read-only: shown in both units.
const RIDE = RIDES.EXPORT_B

test('the theme button shows the mode in use and switches it', async ({ page }) => {
  const settings = new SettingsPage(page)
  const { header } = settings
  // The theme is set on the page's root element as data-theme.
  const root = page.locator('html')

  await test.step('A dark system starts in dark mode: the moon', async () => {
    await page.emulateMedia({ colorScheme: 'dark' })
    await settings.goto()
    await expect(header.theme).toHaveAccessibleName('Dark mode')
    await expect(settings.theme, {
      message: 'The Settings toggle should match the header',
    }).toHaveAccessibleName('Dark mode')
  })

  await test.step('A light system starts in light mode: the sun', async () => {
    await page.emulateMedia({ colorScheme: 'light' })
    await expect(header.theme).toHaveAccessibleName('Light mode')
  })

  await test.step('Hovering names the mode', async () => {
    await expect(header.themeHint, { message: 'The hint should only show on hover' }).toBeHidden()
    await header.theme.hover()
    await expect(header.themeHint).toHaveText('Light mode')
  })

  await test.step('Click: dark mode, and the moon replaces the sun', async () => {
    await header.theme.click()
    await expect(header.theme).toHaveAccessibleName('Dark mode')
    await expect(header.themeHint).toHaveText('Dark mode')
    await expect(root).toHaveAttribute('data-theme', 'dark')
    await expect(settings.theme).toHaveAccessibleName('Dark mode')
  })

  await test.step('Still dark after a reload and on other pages', async () => {
    await page.reload()
    await expect(header.theme).toHaveAccessibleName('Dark mode')
    await header.libraryLink.click()
    await expect(root).toHaveAttribute('data-theme', 'dark')
  })

  await test.step('Click again: light, even on a dark system', async () => {
    await header.theme.click()
    await page.emulateMedia({ colorScheme: 'dark' })
    await expect(root).toHaveAttribute('data-theme', 'light')
    await expect(header.theme, {
      message: 'A choice made in the app should win over the system',
    }).toHaveAccessibleName('Light mode')
  })
})

test('metric units are switched in Settings and apply everywhere', async ({ page }) => {
  const settings = new SettingsPage(page)
  const library = new LibraryPage(page)

  await test.step('The header has no units switch', async () => {
    await library.goto()
    await expect(library.header.root.getByRole('switch', { name: 'Metric units' }), {
      message: 'Units should be switched in Settings only',
    }).toHaveCount(0)
  })

  await test.step('Switch to metric in Settings', async () => {
    await library.header.settingsLink.click()
    await settings.metricUnits.click()
    await expect(settings.metricUnits).toBeChecked()
  })

  await test.step('The library shows kilometres', async () => {
    await settings.header.libraryLink.click()
    await expect(library.row(RIDE.name)).toContainText('13.3 km')
  })

  await test.step('Back to imperial', async () => {
    await library.header.settingsLink.click()
    await settings.metricUnits.click()
    await settings.header.libraryLink.click()
    await expect(library.row(RIDE.name)).toContainText('8.3 mi')
  })
})
