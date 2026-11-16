import { expect, type APIRequestContext } from '@playwright/test'

// Quick set-up and clean-up through the e2e-only routes (src/fitlib/api/routers/e2e.py,
// on only when scripts/e2e-server runs). Use these to get to a known starting point;
// anything a spec is testing must still go through the UI, and every change made here is
// also tested in the UI somewhere (see the README). The exception is `deleteRide`: the app
// can't delete rides yet.
//
//   test('...', async ({ page, request }) => {
//     const testData = new TestData(request)
//     const id = await testData.rideId(RIDES.ZWIFT.file)

export class TestData {
  readonly request: APIRequestContext

  constructor(request: APIRequestContext) {
    this.request = request
  }

  // Every ride's id, by source file name. Ids are random each time the server starts.
  async rideIds(): Promise<Record<string, string>> {
    const response = await this.request.get('/e2e/rides')
    this.check(response.ok(), 'GET /e2e/rides', response.status())
    return (await response.json()) as Record<string, string>
  }

  // One ride's id, or undefined if it isn't in the library.
  async findRideId(file: string): Promise<string | undefined> {
    return (await this.rideIds())[file]
  }

  async rideId(file: string): Promise<string> {
    const id = await this.findRideId(file)
    expect(id, `${file} should be in the library`).toBeDefined()
    return id!
  }

  // Undoes every edit to a ride (name, notes, effort, tags, bike).
  async resetMeta(rideId: string) {
    await this.post(`rides/${rideId}/reset-meta`)
  }

  // Deletes a ride and its files, so the same file can be imported again.
  async deleteRide(rideId: string) {
    await this.post(`rides/${rideId}/delete`)
  }

  private async post(path: string) {
    const response = await this.request.post(`/e2e/${path}`)
    this.check(response.ok(), `POST /e2e/${path}`, response.status())
  }

  private check(ok: boolean, call: string, status: number) {
    expect(
      ok,
      `${call} returned ${status}. Is the server running in e2e mode (scripts/e2e-server)?`,
    ).toBe(true)
  }
}
