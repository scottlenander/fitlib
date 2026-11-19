import type { Locator, Page } from '@playwright/test'
import { Header } from './components/header'
import { Stats } from './components/stats'

// The trends page (/trends): the range (presets, or From and To dates) and grouping, the
// summary figures, and a section per trend (fitness, volume, FTP, efficiency, best efforts),
// each with a chart and a "Show table" disclosure holding its numbers.
export class TrendsPage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  readonly range: Locator
  readonly from: Locator
  readonly to: Locator
  readonly groupBy: Locator
  // "Mon 18 Aug 2025 to Sun 31 Aug 2025. …"
  readonly rangeText: Locator
  readonly summary: Stats
  readonly error: Locator
  readonly fitness: Locator
  readonly fitnessChart: Locator
  readonly fitnessTable: Locator
  // "N rides have no TSS …", under the fitness chart when any ride in the range has none.
  readonly withoutTss: Locator
  readonly volume: Locator
  readonly volumeMetric: Locator
  readonly volumeChart: Locator
  readonly volumeTable: Locator
  readonly ftp: Locator
  readonly ftpChart: Locator
  readonly ftpTable: Locator
  readonly efficiency: Locator
  readonly efficiencyChart: Locator
  readonly efficiencyTable: Locator
  readonly best: Locator
  readonly bestKind: Locator
  readonly bestAgainst: Locator
  readonly bestChart: Locator
  // Captioned "Best efforts: This range against <comparison>".
  readonly bestTable: Locator

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { name: 'Trends', level: 1 })
    const controls = page.getByRole('group', { name: 'Range' })
    this.range = controls.getByRole('radiogroup', { name: 'Range' })
    this.from = controls.getByLabel('From', { exact: true })
    this.to = controls.getByLabel('To', { exact: true })
    this.groupBy = controls.getByRole('combobox', { name: /^Group by/ })
    this.rangeText = page.getByTestId('trends-range')
    this.summary = new Stats(page, 'trends-summary')
    this.error = page.getByTestId('form-error')

    this.fitness = page.getByRole('region', { name: 'Fitness and fatigue', exact: true })
    this.fitnessChart = this.fitness.getByTestId('fitness-chart')
    this.fitnessTable = this.fitness.getByRole('table')
    this.withoutTss = this.fitness.getByTestId('without-tss')

    this.volume = page.getByRole('region', { name: 'Volume', exact: true })
    this.volumeMetric = this.volume.getByRole('combobox', { name: /^Show/ })
    this.volumeChart = this.volume.getByTestId('volume-chart')
    this.volumeTable = this.volume.getByRole('table')

    this.ftp = page.getByRole('region', { name: 'FTP', exact: true })
    this.ftpChart = this.ftp.getByTestId('ftp-chart')
    this.ftpTable = this.ftp.getByRole('table')

    this.efficiency = page.getByRole('region', { name: 'Efficiency', exact: true })
    this.efficiencyChart = this.efficiency.getByTestId('efficiency-chart')
    this.efficiencyTable = this.efficiency.getByRole('table', { name: 'Efficiency of each ride' })

    this.best = page.getByRole('region', { name: 'Best efforts', exact: true })
    this.bestKind = this.best.getByRole('combobox', { name: /^Show/ })
    this.bestAgainst = this.best.getByRole('combobox', { name: /^Against/ })
    this.bestChart = this.best.getByTestId('best-curve-chart')
    this.bestTable = this.best.getByRole('table')
  }

  // Opens the page, with URL parameters such as { since: '2025-08-18', until: '2025-08-31' }.
  async goto(params: Record<string, string> = {}) {
    const search = new URLSearchParams(params).toString()
    await this.page.goto(`/trends${search ? `?${search}` : ''}`)
  }

  preset(label: string): Locator {
    return this.range.getByRole('radio', { name: label, exact: true })
  }

  // A section's "Show table" disclosure (named "Show table: <table>" for screen readers).
  showTable(section: Locator): Locator {
    return section.getByText('Show table')
  }

  // A table row by its row header, e.g. row(trends.volumeTable, 'Week of 18 Aug 2025').
  row(table: Locator, header: string): Locator {
    return table.getByRole('row').filter({
      has: this.page.getByRole('rowheader', { name: header, exact: true }),
    })
  }
}
