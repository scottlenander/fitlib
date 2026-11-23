// The library's "Edit rides" form: what it sends to change several rides at once.
import { parseTags } from './tags'

// Effort: '' keeps it, 'clear' removes it, '1'-'10' sets it. Bike: '' keeps it, 'none'
// removes it, else a bike id. Tags are typed comma-separated.
export type BulkForm = { effort: string; bike: string; add: string; remove: string }

export const KEEP_ALL: BulkForm = { effort: '', bike: '', add: '', remove: '' }

export type BulkChange = {
  rpe?: number | null
  bike_id?: string | null
  add_tags: string[]
  remove_tags: string[]
}

// The change the form asks for, or null if it leaves everything as it is. Fields kept are
// left out, as the API keeps what it isn't sent.
export function bulkChange(form: BulkForm): BulkChange | null {
  const change: BulkChange = { add_tags: parseTags(form.add), remove_tags: parseTags(form.remove) }
  if (form.effort) change.rpe = form.effort === 'clear' ? null : Number(form.effort)
  if (form.bike) change.bike_id = form.bike === 'none' ? null : form.bike
  const empty =
    !('rpe' in change) &&
    !('bike_id' in change) &&
    change.add_tags.length === 0 &&
    change.remove_tags.length === 0
  return empty ? null : change
}

// "1 ride" or "12 rides".
export function rideCount(count: number): string {
  return count === 1 ? '1 ride' : `${count} rides`
}

// Said when selected rides turned out to be gone (deleted in another tab or from the command
// line): they're unselected and nothing was changed.
export function missingText(count: number): string {
  return count === 1
    ? '1 selected ride is no longer in the library and was unselected. Nothing was changed: try again.'
    : `${count} selected rides are no longer in the library and were unselected. Nothing was changed: try again.`
}
