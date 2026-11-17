import type { Locator, Page } from '@playwright/test'

// The zoom under a stacked chart (ride page and compare page): a label saying how to zoom
// (drag the bar's ends, or scroll on a chart) and "Show whole ride", enabled while zoomed in.
// Each page has one stacked chart, so these aren't scoped further.
export class ChartZoom {
  readonly page: Page
  readonly hint: Locator
  readonly showWholeRide: Locator

  constructor(page: Page) {
    this.page = page
    this.hint = page.getByText(/^Zoom: drag the ends of the bar under the charts/)
    this.showWholeRide = page.getByRole('button', { name: 'Show whole ride' })
  }

  // Zooms in by scrolling up over the middle of a chart, as a person with a mouse would.
  async zoomIn(chart: Locator) {
    await chart.scrollIntoViewIfNeeded()
    const box = await chart.boundingBox()
    if (!box) throw new Error('The chart should be on the page to zoom in on it')
    await this.page.mouse.move(box.x + box.width / 2, box.y + 80)
    await this.page.mouse.wheel(0, -500)
  }
}
