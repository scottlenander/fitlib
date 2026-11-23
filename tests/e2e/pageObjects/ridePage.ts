import type { Locator, Page } from '@playwright/test'
import { ChartZoom } from './components/chartZoom'
import { ConfirmDelete } from './components/confirmDelete'
import { Header } from './components/header'
import { RouteMap } from './components/routeMap'
import { RouteProgress } from './components/routeProgress'
import { SimilarRides } from './components/similarRides'
import { Stats } from './components/stats'

// One ride (/rides/:id): summary and training cards, Ride Stats charts (over time or
// distance, zoomable), zones, best efforts, laps.
// Sections only appear when the ride has the data (no power → no zones or power figures).
export class RidePage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  // "Tue 05 Aug 2025, 19:00 · Garmin · Garmin Edge 540 · Outdoor"
  readonly subtitle: Locator
  // Under the subtitle: where the start time's time zone came from ("Local time from the
  // device.", or the default or UTC, with a link to Settings).
  readonly timeZoneNote: Locator
  readonly summary: Stats
  readonly training: Stats
  readonly details: Stats
  readonly statsHeading: Locator
  readonly traceChart: Locator
  // The trace chart's x axis: time from the start or distance ridden.
  readonly overTime: Locator
  readonly overDistance: Locator
  readonly zoom: ChartZoom
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
  // Beside Ride Stats, for rides with positions.
  readonly map: RouteMap
  readonly similar: SimilarRides
  readonly progress: RouteProgress
  readonly notFound: Locator
  // In Details, next to Edit details; opens the confirm dialog.
  readonly deleteButton: Locator
  readonly confirmDelete: ConfirmDelete
  readonly backToLibrary: Locator

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { level: 1 })
    this.subtitle = page.getByTestId('ride-subtitle')
    this.timeZoneNote = page.getByTestId('time-zone-note')
    this.summary = new Stats(page, 'summary-stats')
    this.training = new Stats(page, 'training-stats')
    this.details = new Stats(page, 'detail-stats')
    this.statsHeading = page.getByRole('heading', { name: 'Ride Stats', level: 2 })
    this.traceChart = page.getByTestId('trace-chart')
    const over = page.getByRole('radiogroup', { name: 'Show over' })
    this.overTime = over.getByRole('radio', { name: 'Time' })
    this.overDistance = over.getByRole('radio', { name: 'Distance' })
    this.zoom = new ChartZoom(page)
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
    this.map = new RouteMap(page, 'route-map', 'map-note')
    this.similar = new SimilarRides(page)
    this.progress = new RouteProgress(page)
    this.notFound = page.getByRole('heading', { name: 'Ride not found', level: 1 })
    this.deleteButton = page.getByRole('button', { name: 'Delete ride' })
    this.confirmDelete = new ConfirmDelete(page)
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
