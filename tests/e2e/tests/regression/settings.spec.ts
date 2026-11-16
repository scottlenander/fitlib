import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { SettingsPage } from '../../pageObjects/settingsPage'
import { RIDES } from '../../libs/constants'

// Read-only: shown in both units.
const RIDE = RIDES.EXPORT_B

test('the theme follows the system until a sun or moon is chosen', async ({ page }) => {
  const settings = new SettingsPage(page)
  const { header } = settings
  // The theme is set on the page's root element as data-theme.
  const root = page.locator('html')

  await test.step('A dark system starts in dark mode', async () => {
    await page.emulateMedia({ colorScheme: 'dark' })
    await settings.goto()
    await expect(header.darkMode).toHaveAttribute('aria-pressed', 'true')
    await expect(settings.darkMode, {
      message: 'The Settings toggle should match the header',
    }).toHaveAttribute('aria-pressed', 'true')
  })

  await test.step('A light system starts in light mode', async () => {
    await page.emulateMedia({ colorScheme: 'light' })
    await expect(header.lightMode).toHaveAttribute('aria-pressed', 'true')
    await expect(header.darkMode).toHaveAttribute('aria-pressed', 'false')
  })

  await test.step('Hovering the moon names it', async () => {
    await expect(header.hint(header.darkMode), {
      message: 'The hint should only show on hover',
    }).toBeHidden()
    await header.darkMode.hover()
    await expect(header.hint(header.darkMode)).toHaveText('Dark mode')
    await header.lightMode.hover()
    await expect(header.hint(header.lightMode)).toHaveText('Light mode')
  })

  await test.step('Choose the moon', async () => {
    await header.darkMode.click()
    await expect(settings.darkMode).toHaveAttribute('aria-pressed', 'true')
    await expect(root).toHaveAttribute('data-theme', 'dark')
  })

  await test.step('Still dark after a reload and on other pages', async () => {
    await page.reload()
    await expect(header.darkMode).toHaveAttribute('aria-pressed', 'true')
    await header.libraryLink.click()
    await expect(root).toHaveAttribute('data-theme', 'dark')
  })

  await test.step('Choose the sun: light even on a dark system', async () => {
    await header.lightMode.click()
    await page.emulateMedia({ colorScheme: 'dark' })
    await expect(root).toHaveAttribute('data-theme', 'light')
    await expect(header.lightMode, {
      message: 'A choice made in the app should win over the system',
    }).toHaveAttribute('aria-pressed', 'true')
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
