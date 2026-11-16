import { expect, type Locator, type Page } from '@playwright/test'
import { Header } from './components/header'
import { Stats } from './components/stats'

export type AthleteValues = { from: string; ftp?: string; weight?: string; maxHr?: string }

// Settings (/settings): the light/dark toggle (also in the header), the units switch (only
// here) and the athlete history.
// The history table only appears once there is an entry.
export class SettingsPage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  readonly display: Locator
  readonly lightMode: Locator
  readonly darkMode: Locator
  readonly metricUnits: Locator
  readonly today: Stats
  readonly history: Locator
  readonly form: Locator
  readonly from: Locator
  readonly ftp: Locator
  // "Weight (lb)" or "Weight (kg)", in the display units.
  readonly weight: Locator
  readonly maxHr: Locator
  readonly saveButton: Locator
  readonly notice: Locator
  readonly error: Locator

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { name: 'Settings', level: 1 })
    this.display = page.getByTestId('display-settings')
    this.lightMode = this.display.getByRole('button', { name: 'Light mode' })
    this.darkMode = this.display.getByRole('button', { name: 'Dark mode' })
    this.metricUnits = this.display.getByRole('switch', { name: 'Metric units' })
    this.today = new Stats(page, 'athlete-today')
    this.history = page.getByRole('table', { name: 'Athlete history' })
    this.form = page.getByTestId('athlete-form')
    this.from = this.form.getByLabel('From')
    this.ftp = this.form.getByLabel('FTP (W)')
    this.weight = this.form.getByLabel(/^Weight/)
    this.maxHr = this.form.getByLabel('Max heart rate (bpm)')
    this.saveButton = this.form.getByRole('button', { name: 'Save values' })
    this.notice = this.form.getByTestId('form-notice')
    this.error = this.form.getByTestId('form-error')
  }

  async goto() {
    await this.page.goto('/settings')
  }

  // One history row, found by its date.
  entry(from: string): Locator {
    return this.history
      .getByRole('row')
      .filter({ has: this.page.getByRole('rowheader', { name: from, exact: true }) })
  }

  removeButton(from: string): Locator {
    return this.page.getByRole('button', { name: `Remove values from ${from}` })
  }

  // Fills in the values form and saves it; fields left out stay empty.
  async saveValues(values: AthleteValues) {
    await this.from.fill(values.from)
    await this.ftp.fill(values.ftp ?? '')
    await this.weight.fill(values.weight ?? '')
    await this.maxHr.fill(values.maxHr ?? '')
    await this.saveButton.click()
  }

  // Removes an entry, accepting the confirmation, and waits for its row to go.
  async removeEntry(from: string) {
    this.page.once('dialog', (dialog) => void dialog.accept())
    await this.removeButton(from).click()
    await expect(this.entry(from)).toHaveCount(0)
  }
}
