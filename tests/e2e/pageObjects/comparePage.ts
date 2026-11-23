import type { Locator, Page } from '@playwright/test'
import { ChartZoom } from './components/chartZoom'
import { Header } from './components/header'
import { RouteMap } from './components/routeMap'

// The compare page (/compare?ids=a,b[,c,d]): the rides with a Remove button each, how they're
// lined up, the figures table (one column per ride) and the charts. The time gap chart only
// shows when the rides are lined up by distance.
export class ComparePage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  // The rides compared, in order, each with its link and Remove button.
  readonly rides: Locator
  readonly view: Locator
  readonly alignDistance: Locator
  readonly alignTime: Locator
  readonly smoothing: Locator
  readonly table: Locator
  readonly traces: Locator
  readonly zoom: ChartZoom
  readonly gapChart: Locator
  readonly curves: Locator
  // The routes of the rides in one place, each in its ride's colour; the others listed.
  readonly map: RouteMap
  // "Pick at least 2 rides to compare: …" when fewer than 2 rides are in the URL.
  readonly empty: Locator
  readonly error: Locator
  // "Left out 1 ride that is no longer in the library."
  readonly leftOut: Locator

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { name: 'Compare rides', level: 1 })
    this.rides = page.getByRole('list', { name: 'Rides compared' }).getByTestId('compare-ride')
    this.view = page.getByRole('group', { name: 'View' })
    this.alignDistance = this.view.getByRole('radio', { name: 'Distance' })
    this.alignTime = this.view.getByRole('radio', { name: 'Time' })
    this.smoothing = this.view.getByLabel('Smoothing')
    this.table = page.getByRole('table', { name: 'Compared figures' })
    this.traces = page.getByTestId('compare-traces')
    this.zoom = new ChartZoom(page)
    this.gapChart = page.getByTestId('gap-chart')
    this.curves = page.getByTestId('compare-curves')
    this.map = new RouteMap(page, 'compare-map', 'compare-map-note')
    this.empty = page.getByTestId('compare-empty')
    this.error = page.getByTestId('form-error')
    this.leftOut = page.getByTestId('left-out-notice')
  }

  // Opens a comparison of rides by id, the first being the one gaps are measured against.
  async goto(ids: string[]) {
    await this.page.goto(`/compare?ids=${ids.join(',')}`)
  }

  remove(name: string): Locator {
    return this.page.getByRole('button', { name: `Remove ${name}`, exact: true })
  }

  // A figure for one ride: the row's label (e.g. "Distance") and the ride's column, from 0.
  figure(label: string, ride: number): Locator {
    return this.table
      .getByRole('row', { name: new RegExp(`^${label} `) })
      .getByRole('cell')
      .nth(ride)
  }

  // The figures table's column heads, one per ride, in order.
  columnHeads(): Locator {
    return this.table.getByRole('columnheader')
  }
}
