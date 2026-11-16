import type { Locator, Page } from '@playwright/test'
import { Header } from './components/header'
import { Stats } from './components/stats'

// One ride (/rides/:id): summary and training cards, charts, zones, best efforts, laps.
// Sections only appear when the ride has the data (no power → no zones or power figures).
export class RidePage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  // "Tue 05 Aug 2025, 19:00 · Garmin · Garmin Edge 540 · Outdoor"
  readonly subtitle: Locator
  readonly summary: Stats
  readonly training: Stats
  readonly details: Stats
  readonly traceChart: Locator
  readonly powerZones: Locator
  readonly hrZones: Locator
  readonly curveChart: Locator
  readonly efforts: Locator
  readonly laps: Locator
  readonly notes: Locator
  readonly editButton: Locator
  readonly editForm: Locator
  readonly editName: Locator
  readonly editEffort: Locator
  readonly editBike: Locator
  // Tags typed as one line, separated by commas.
  readonly editTags: Locator
  readonly editNotes: Locator
  readonly saveButton: Locator
  readonly cancelButton: Locator
  readonly saved: Locator
  readonly editError: Locator
  // "No bike, effort, tags or notes yet."
  readonly noDetails: Locator
  readonly notFound: Locator
  readonly backToLibrary: Locator

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { level: 1 })
    this.subtitle = page.getByTestId('ride-subtitle')
    this.summary = new Stats(page, 'summary-stats')
    this.training = new Stats(page, 'training-stats')
    this.details = new Stats(page, 'detail-stats')
    this.traceChart = page.getByTestId('trace-chart')
    this.powerZones = page.getByRole('table', { name: 'Power zones' })
    this.hrZones = page.getByRole('table', { name: 'Heart-rate zones' })
    this.curveChart = page.getByTestId('curve-chart')
    this.efforts = page.getByRole('table', { name: 'Best efforts' })
    this.laps = page.getByRole('table', { name: 'Laps' })
    this.notes = page.getByTestId('ride-notes')
    this.editButton = page.getByRole('button', { name: 'Edit details' })
    this.editForm = page.getByRole('form', { name: 'Edit details' })
    this.editName = this.editForm.getByLabel('Name')
    this.editEffort = this.editForm.getByLabel('Effort')
    this.editBike = this.editForm.getByLabel('Bike')
    this.editTags = this.editForm.getByLabel('Tags')
    this.editNotes = this.editForm.getByLabel('Notes')
    this.saveButton = this.editForm.getByRole('button', { name: 'Save' })
    this.cancelButton = this.editForm.getByRole('button', { name: 'Cancel' })
    this.saved = page.getByTestId('form-notice')
    this.editError = this.editForm.getByTestId('form-error')
    this.noDetails = page.getByText('No bike, effort, tags or notes yet.')
    this.notFound = page.getByRole('heading', { name: 'Ride not found', level: 1 })
    this.backToLibrary = page.getByRole('link', { name: 'Back to the library' })
  }

  async goto(rideId: string) {
    await this.page.goto(`/rides/${rideId}`)
  }

  // A zone's row, e.g. zone(this.powerZones, 'Z2').
  zone(table: Locator, zone: string): Locator {
    return table.getByRole('row').filter({ has: this.page.getByRole('rowheader', { name: zone }) })
  }

  // A best-effort row, e.g. effort('20 min').
  effort(duration: string): Locator {
    return this.efforts
      .getByRole('row')
      .filter({ has: this.page.getByRole('rowheader', { name: duration, exact: true }) })
  }

  lapRows(): Locator {
    return this.laps.getByRole('rowheader')
  }
}
