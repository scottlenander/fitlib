import type { Locator, Page } from '@playwright/test'

// A route map (Leaflet), on a ride's page or the compare page. The drawing is Leaflet's, so
// what's on it is read from the map's data attributes: data-routes (how many routes),
// data-street-map, data-cursor (the dot for the moment pointed at in Ride Stats) and
// data-span (the stretch Ride Stats is zoomed to), each "on" or "off".
export class RouteMap {
  readonly section: Locator
  readonly heading: Locator
  // The map itself; its accessible name says what it shows.
  readonly map: Locator
  // Under the map: Zwift world, no street map (with a link to Settings), or the credit.
  readonly note: Locator
  readonly settingsLink: Locator
  readonly credit: Locator

  constructor(page: Page, testId: string, noteTestId: string) {
    this.section = page.getByRole('region', { name: 'Map', exact: true })
    this.heading = page.getByRole('heading', { name: 'Map', level: 2 })
    this.map = page.getByTestId(testId)
    this.note = page.getByTestId(noteTestId)
    this.settingsLink = this.note.getByRole('link', { name: 'Turn on the street map in Settings' })
    this.credit = this.map.getByRole('link', { name: 'OpenStreetMap' })
  }
}
