// Searching and filtering the library.
import { useState, type FormEvent } from 'react'
import { useBikes } from '../api/bikes'
import { useTags } from '../api/rides'
import { useZwiftWorlds } from '../api/settings'
import { NO_FILTERS, withSource, withWorld, type LibraryState } from './libraryQuery'

export function SearchBox({
  initial,
  onSearch,
}: {
  initial: string
  onSearch: (q: string) => void
}) {
  const [text, setText] = useState(initial)
  function submit(event: FormEvent) {
    event.preventDefault()
    onSearch(text)
  }
  return (
    <form role="search" onSubmit={submit} className="search">
      <label htmlFor="ride-search">Search</label>
      <input
        id="ride-search"
        type="search"
        value={text}
        placeholder="Name, notes, tags, bike or device"
        onChange={(e) => setText(e.target.value)}
      />
      <button type="submit">Search</button>
    </form>
  )
}

type FiltersProps = {
  state: LibraryState
  onChange: (changes: Partial<LibraryState>) => void
}

const EFFORTS = Array.from({ length: 10 }, (_, i) => String(i + 1))

export function Filters({ state, onChange }: FiltersProps) {
  const tags = useTags()
  const bikes = useBikes()
  const worlds = useZwiftWorlds()
  return (
    <fieldset className="filters">
      <legend>Filters</legend>
      <label>
        Source
        <select
          value={state.source}
          onChange={(e) => onChange(withSource(e.target.value as LibraryState['source']))}
        >
          <option value="">Any</option>
          <option value="zwift">Zwift</option>
          <option value="garmin">Garmin</option>
          <option value="other">Other</option>
        </select>
      </label>
      <label>
        Where
        <select
          value={state.where}
          onChange={(e) => onChange({ where: e.target.value as LibraryState['where'] })}
        >
          <option value="">Anywhere</option>
          <option value="indoor">Indoor</option>
          <option value="outdoor">Outdoor</option>
        </select>
      </label>
      <label>
        Power
        <select
          value={state.power}
          onChange={(e) => onChange({ power: e.target.value as LibraryState['power'] })}
        >
          <option value="">Any</option>
          <option value="yes">With power</option>
          <option value="no">Without power</option>
        </select>
      </label>
      <label>
        From
        <input
          type="date"
          value={state.since}
          onChange={(e) => onChange({ since: e.target.value })}
        />
      </label>
      <label>
        To
        <input
          type="date"
          value={state.until}
          onChange={(e) => onChange({ until: e.target.value })}
        />
      </label>
      <label>
        At least (minutes)
        <input
          type="number"
          min={0}
          inputMode="numeric"
          value={state.minMinutes}
          onChange={(e) => onChange({ minMinutes: e.target.value })}
        />
      </label>
      <label>
        Tag
        <select value={state.tag} onChange={(e) => onChange({ tag: e.target.value })}>
          <option value="">Any</option>
          {tags.data?.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name}
            </option>
          ))}
          {/* A tag from the URL that no ride has any more. */}
          {state.tag && !tags.data?.some((t) => t.name === state.tag) && (
            <option value={state.tag}>{state.tag}</option>
          )}
        </select>
      </label>
      <label>
        Bike
        <select value={state.bike} onChange={(e) => onChange({ bike: e.target.value })}>
          <option value="">Any</option>
          <option value="none">No bike</option>
          {bikes.data?.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Effort from
        <select value={state.minRpe} onChange={(e) => onChange({ minRpe: e.target.value })}>
          <option value="">Any</option>
          {EFFORTS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <label>
        Effort to
        <select value={state.maxRpe} onChange={(e) => onChange({ maxRpe: e.target.value })}>
          <option value="">Any</option>
          {EFFORTS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <label>
        World
        <select value={state.world} onChange={(e) => onChange(withWorld(state, e.target.value))}>
          <option value="">Any</option>
          {worlds.data?.map((w) => (
            <option key={w.slug} value={w.slug}>
              {w.name}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={() => onChange(NO_FILTERS)}>
        Clear filters
      </button>
    </fieldset>
  )
}
