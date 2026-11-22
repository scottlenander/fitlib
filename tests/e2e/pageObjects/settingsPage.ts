import { expect, type Locator, type Page } from '@playwright/test'
import { Header, THEME_NAME } from './components/header'
import { NewRidesNotice } from './components/newRidesNotice'
import { Stats } from './components/stats'

export type AthleteValues = {
  from: string
  ftp?: string
  weight?: string
  maxHr?: string
  thresholdHr?: string
}

// Settings (/settings): the light/dark toggle (also in the header), the units switch (only
// here), the default time zone, the watched folders and the athlete history.
// Watched folders: the list (each with its state, files found and a Stop watching button),
// the form to add one, Scan now (once there's a folder) and the latest files table (once a
// file that wasn't already in the library has been found).
// The history table only appears once there is an entry.
export class SettingsPage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  readonly display: Locator
  // Named "Light mode" or "Dark mode", the mode in use; clicking switches mode.
  readonly theme: Locator
  readonly metricUnits: Locator
  readonly timeZoneForm: Locator
  // The default time zone list: "None (show UTC)" or an IANA name such as America/New_York.
  readonly timeZone: Locator
  // "Use this computer's time zone (…)", naming the browser's zone.
  readonly useComputersZone: Locator
  readonly saveTimeZone: Locator
  // "Saved: America/New York. 1 ride updated."
  readonly timeZoneNotice: Locator
  readonly newRides: NewRidesNotice
  readonly watched: Locator
  readonly watchedFolders: Locator
  readonly noWatchedFolders: Locator
  readonly folderToWatch: Locator
  readonly watchButton: Locator
  readonly watchError: Locator
  // "Watching <path>. Rides already in it are being imported."
  readonly watchNotice: Locator
  readonly scanNow: Locator
  // "Looking for new rides in the watched folders…" with the server's watcher running.
  readonly scanResult: Locator
  readonly latestFiles: Locator
  readonly today: Stats
  readonly history: Locator
  readonly form: Locator
  readonly from: Locator
  readonly ftp: Locator
  // "Weight (lb)" or "Weight (kg)", in the display units.
  readonly weight: Locator
  readonly maxHr: Locator
  readonly thresholdHr: Locator
  readonly saveButton: Locator
  readonly notice: Locator
  readonly error: Locator
  // The year of birth form, under today's values.
  readonly birthYearForm: Locator
  readonly birthYear: Locator
  readonly saveBirthYear: Locator
  // "Saved: born 2026. Estimated threshold heart rate today: 187 bpm." or "Year of birth
  // cleared."
  readonly birthYearNotice: Locator
  readonly birthYearError: Locator

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { name: 'Settings', level: 1 })
    this.display = page.getByTestId('display-settings')
    this.theme = this.display.getByRole('button', { name: THEME_NAME })
    this.metricUnits = this.display.getByRole('switch', { name: 'Metric units' })
    this.timeZoneForm = page.getByTestId('timezone-form')
    this.timeZone = this.timeZoneForm.getByLabel('Default time zone')
    this.useComputersZone = this.timeZoneForm.getByRole('button', {
      name: /^Use this computer's time zone/,
    })
    this.saveTimeZone = this.timeZoneForm.getByRole('button', { name: 'Save time zone' })
    this.timeZoneNotice = this.timeZoneForm.getByTestId('form-notice')
    this.newRides = new NewRidesNotice(page)
    this.watched = page.getByRole('region', { name: 'Watched folders', exact: true })
    this.watchedFolders = this.watched.getByTestId('watch-folder')
    this.noWatchedFolders = this.watched.getByTestId('watch-empty')
    this.folderToWatch = this.watched.getByLabel('Folder to watch')
    this.watchButton = this.watched.getByRole('button', { name: 'Watch folder', exact: true })
    this.watchError = this.watched.getByTestId('form-error')
    this.watchNotice = this.watched.getByTestId('form-notice')
    this.scanNow = this.watched.getByRole('button', { name: 'Scan now' })
    this.scanResult = this.watched.getByTestId('scan-result')
    this.latestFiles = this.watched.getByRole('table', {
      name: 'Latest files from watched folders',
    })
    this.today = new Stats(page, 'athlete-today')
    this.history = page.getByRole('table', { name: 'Athlete history' })
    this.form = page.getByTestId('athlete-form')
    this.from = this.form.getByLabel('From')
    this.ftp = this.form.getByLabel('FTP (W)')
    this.weight = this.form.getByLabel(/^Weight/)
    this.maxHr = this.form.getByLabel('Max heart rate (bpm)')
    this.thresholdHr = this.form.getByLabel('Threshold heart rate (bpm)')
    this.saveButton = this.form.getByRole('button', { name: 'Save values' })
    this.notice = this.form.getByTestId('form-notice')
    this.error = this.form.getByTestId('form-error')
    this.birthYearForm = page.getByTestId('birth-year-form')
    this.birthYear = this.birthYearForm.getByLabel('Year of birth')
    this.saveBirthYear = this.birthYearForm.getByRole('button', { name: 'Save year of birth' })
    this.birthYearNotice = this.birthYearForm.getByTestId('form-notice')
    this.birthYearError = this.birthYearForm.getByTestId('form-error')
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

  // A watched folder's row, by its path.
  watchedFolder(folder: string): Locator {
    return this.watchedFolders.filter({ hasText: folder })
  }

  stopWatching(folder: string): Locator {
    return this.watched.getByRole('button', { name: `Stop watching ${folder}`, exact: true })
  }

  // A row of the latest files table, by file name.
  latestFile(name: string): Locator {
    return this.latestFiles
      .getByRole('row')
      .filter({ has: this.page.getByRole('rowheader', { name, exact: true }) })
  }

  // Types a folder's path and watches it.
  async watchFolder(folder: string) {
    await this.folderToWatch.fill(folder)
    await this.watchButton.click()
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
    await this.thresholdHr.fill(values.thresholdHr ?? '')
    await this.saveButton.click()
  }

  // Sets the year of birth; an empty string clears it.
  async setBirthYear(year: string) {
    await this.birthYear.fill(year)
    await this.saveBirthYear.click()
  }

  // Removes an entry, accepting the confirmation, and waits for its row to go.
  async removeEntry(from: string) {
    this.page.once('dialog', (dialog) => void dialog.accept())
    await this.removeButton(from).click()
    await expect(this.entry(from)).toHaveCount(0)
  }
}
