import { expect, type Locator, type Page } from '@playwright/test'
import { Header } from './components/header'

// Bikes (/bikes): the bikes table, adding a bike, the default-bike timeline and applying
// defaults to existing rides. Retired bikes are hidden until "Show retired bikes" is ticked
// (the box only appears once a bike is retired).
export class BikesPage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  readonly table: Locator
  readonly showRetired: Locator
  readonly addForm: Locator
  readonly addName: Locator
  readonly addKind: Locator
  readonly addButton: Locator
  readonly addNotice: Locator
  readonly addError: Locator
  readonly defaults: Locator
  readonly defaultForm: Locator
  readonly defaultRides: Locator
  readonly defaultFrom: Locator
  readonly defaultBike: Locator
  readonly setDefaultButton: Locator
  readonly previewButton: Locator
  readonly applyButton: Locator
  // "Would change 1 ride:" then one line per bike, or "Changed ..." after Apply.
  readonly backfillResult: Locator

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { name: 'Bikes', level: 1 })
    this.table = page.getByRole('table', { name: 'Bikes', exact: true })
    this.showRetired = page.getByRole('checkbox', { name: /^Show retired bikes/ })
    this.addForm = page.getByTestId('add-bike-form')
    this.addName = this.addForm.getByLabel('Name')
    this.addKind = this.addForm.getByLabel('Kind')
    this.addButton = this.addForm.getByRole('button', { name: 'Add bike' })
    this.addNotice = this.addForm.getByTestId('form-notice')
    this.addError = this.addForm.getByTestId('form-error')
    this.defaults = page.getByRole('table', { name: 'Default bikes' })
    this.defaultForm = page.getByTestId('default-form')
    this.defaultRides = this.defaultForm.getByLabel('Rides')
    this.defaultFrom = this.defaultForm.getByLabel('From')
    this.defaultBike = this.defaultForm.getByLabel('Bike')
    this.setDefaultButton = this.defaultForm.getByRole('button', { name: 'Set default' })
    this.previewButton = page.getByRole('button', { name: 'Preview' })
    this.applyButton = page.getByRole('button', { name: 'Apply' })
    this.backfillResult = page.getByTestId('backfill-result')
  }

  async goto() {
    await this.page.goto('/bikes')
  }

  // A bike's row, by name; the row header also says "(retired)" for retired bikes.
  row(name: string): Locator {
    return this.page.getByTestId('bike-row').filter({
      has: this.page.getByRole('rowheader', {
        name: new RegExp(`^${escape(name)}( \\(retired\\))?$`),
      }),
    })
  }

  editButton(name: string): Locator {
    return this.page.getByRole('button', { name: `Edit ${name}`, exact: true })
  }

  retireButton(name: string): Locator {
    return this.page.getByRole('button', { name: `Retire ${name}`, exact: true })
  }

  bringBackButton(name: string): Locator {
    return this.page.getByRole('button', { name: `Bring back ${name}`, exact: true })
  }

  // The inline form that replaces a bike's row while it's being edited.
  editForm(name: string): Locator {
    return this.page.getByRole('form', { name: `Edit ${name}` })
  }

  async addBike(name: string, kind?: string) {
    await this.addName.fill(name)
    await this.addKind.selectOption({ label: kind ?? 'Not set' })
    await this.addButton.click()
  }

  // A timeline entry, by its kind of ride ("Indoor (not Zwift)") and date.
  defaultRow(rides: string, from: string): Locator {
    return this.defaults
      .getByRole('row')
      .filter({ has: this.page.getByRole('rowheader', { name: rides, exact: true }) })
      .filter({ has: this.page.getByRole('cell', { name: from, exact: true }) })
  }

  async setDefault(rides: string, from: string, bike: string) {
    await this.defaultRides.selectOption({ label: rides })
    await this.defaultFrom.fill(from)
    await this.defaultBike.selectOption({ label: bike })
    await this.setDefaultButton.click()
  }

  // Removes a timeline entry, accepting the confirmation, and waits for its row to go.
  async removeDefault(rides: string, from: string) {
    this.page.once('dialog', (dialog) => void dialog.accept())
    await this.page.getByRole('button', { name: `Remove ${rides} from ${from}` }).click()
    await expect(this.defaultRow(rides, from)).toHaveCount(0)
  }
}

// Bike names are matched as text, so characters with a meaning in regular expressions are
// escaped.
function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
