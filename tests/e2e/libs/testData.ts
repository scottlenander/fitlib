import fs from 'node:fs'
import { basename } from 'node:path'
import { expect, type APIRequestContext } from '@playwright/test'

// Quick set-up and clean-up through the e2e-only routes (src/fitlib/api/routers/e2e.py,
// on only when scripts/e2e-server runs). Use these to get to a known starting point;
// anything a spec is testing must still go through the UI, and every change made here is
// also tested in the UI somewhere (see the README).
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

  // Deletes a ride and its files, so the same file can be imported again as new. Unlike
  // deleting in the app, the file isn't remembered as deleted.
  async deleteRide(rideId: string) {
    await this.post(`rides/${rideId}/delete`)
  }

  // Imports a file through the app's own import (as the Import page does), for rides kept
  // out of the library at start-up. Imports it even if a run deleted it in the app before.
  // Returns the ride's id.
  async importFile(path: string): Promise<string> {
    const response = await this.request.post('/api/imports?include_deleted=true', {
      multipart: {
        files: {
          name: basename(path),
          mimeType: 'application/octet-stream',
          buffer: fs.readFileSync(path),
        },
      },
    })
    this.check(response.ok(), 'POST /api/imports', response.status())
    return this.rideId(basename(path))
  }

  // Removes the library's default time zone (the time zone spec owns this setting).
  async clearTimeZone() {
    const response = await this.request.put('/api/settings/timezone', {
      data: { timezone: null },
    })
    this.check(response.ok(), 'PUT /api/settings/timezone', response.status())
  }

  // Stops watching the temp folders a watched folders test left behind (one that failed
  // before its clean-up): their names start with `prefix`.
  async stopWatchingLeftovers(prefix: string) {
    const response = await this.request.get('/api/watch')
    this.check(response.ok(), 'GET /api/watch', response.status())
    const { folders } = (await response.json()) as { folders: { path: string }[] }
    for (const { path } of folders.filter((f) => basename(f.path).startsWith(prefix))) {
      const removed = await this.request.delete('/api/watch/folders', { params: { path } })
      this.check(removed.ok(), 'DELETE /api/watch/folders', removed.status())
    }
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
