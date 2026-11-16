import path from 'node:path'
import type { Locator, Page } from '@playwright/test'
import { FIXTURES_DIR } from '../libs/constants'
import { Header } from './components/header'

// Importing rides (/import): choose files, import, and the results grouped like the CLI's.
export class ImportPage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  readonly fileInput: Locator
  readonly chosen: Locator
  readonly importButton: Locator
  // "Imported 1, already in library 0, skipped 0, failed 0."
  readonly summary: Locator
  readonly imported: Locator
  readonly duplicates: Locator
  readonly skipped: Locator
  readonly failed: Locator

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { name: 'Import rides', level: 1 })
    this.fileInput = page.getByLabel('Choose .fit or .zip files')
    this.chosen = page.getByTestId('chosen-files')
    this.importButton = page.getByRole('button', { name: 'Import', exact: true })
    this.summary = page.getByTestId('import-summary')
    this.imported = page.getByTestId('imported-files')
    this.duplicates = page.getByTestId('duplicate-files')
    this.skipped = page.getByTestId('skipped-files')
    this.failed = page.getByTestId('failed-files')
  }

  async goto() {
    await this.page.goto('/import')
  }

  // A fixture file's path, from its name in tests/fixtures/fit.
  fixturePath(file: string): string {
    return path.join(FIXTURES_DIR, file)
  }

  // Chooses fixture files and imports them.
  async importFixtures(...files: string[]) {
    await this.fileInput.setInputFiles(files.map((f) => this.fixturePath(f)))
    await this.importButton.click()
  }
}
