import { test, expect } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { SettingsPage } from '../../pageObjects/settingsPage'
import { RIDES } from '../../libs/constants'

// Read-only: shown in both units.
const RIDE = RIDES.EXPORT_B

test('dark mode follows the system until it is switched', async ({ page }) => {
  const settings = new SettingsPage(page)
  // The theme is set on the page's root element as data-theme.
  const root = page.locator('html')

  await test.step('A dark system starts in dark mode', async () => {
    await page.emulateMedia({ colorScheme: 'dark' })
    await settings.goto()
    await expect(settings.darkMode).toBeChecked()
    await expect(settings.header.darkMode, {
      message: 'The header switch should match the Settings switch',
    }).toBeChecked()
  })

  await test.step('A light system starts in light mode', async () => {
    await page.emulateMedia({ colorScheme: 'light' })
    await expect(settings.darkMode, {
      message: 'With no choice made, dark mode should follow the system',
    }).not.toBeChecked()
  })

  await test.step('Switch dark mode on', async () => {
    await settings.darkMode.click()
    await expect(settings.header.darkMode).toBeChecked()
    await expect(root).toHaveAttribute('data-theme', 'dark')
  })

  await test.step('Still dark after a reload and on other pages', async () => {
    await page.reload()
    await expect(settings.darkMode).toBeChecked()
    await settings.header.libraryLink.click()
    await expect(root).toHaveAttribute('data-theme', 'dark')
  })

  await test.step('Switched off from the header, light even on a dark system', async () => {
    await settings.header.darkMode.click()
    await page.emulateMedia({ colorScheme: 'dark' })
    await expect(root).toHaveAttribute('data-theme', 'light')
    await expect(settings.header.darkMode, {
      message: 'A choice made in the app should win over the system',
    }).not.toBeChecked()
  })
})

test('metric units switched in Settings apply everywhere', async ({ page }) => {
  const settings = new SettingsPage(page)
  const library = new LibraryPage(page)

  await test.step('Switch to metric in Settings', async () => {
    await settings.goto()
    await settings.metricUnits.click()
    await expect(settings.header.metricUnits).toBeChecked()
  })

  await test.step('The library shows kilometres', async () => {
    await settings.header.libraryLink.click()
    await expect(library.row(RIDE.name)).toContainText('13.3 km')
  })

  await test.step('Back to imperial from the header', async () => {
    await library.header.metricUnits.click()
    await expect(library.row(RIDE.name)).toContainText('8.3 mi')
  })
})
