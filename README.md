# Fitlib

A local library for cycling `.fit` files from Zwift and Garmin. It imports rides from folders,
stores them compactly, and summarises each ride in readable numbers, on the command line or in
a browser, finds rides on the same route or with a similar effort, and compares rides side
by side. Later phases add fitness trends.

The project is built in phases. Phase 1a added the core: importing, storage, basic ride
figures and a command line. Phase 1b added training figures (NP, IF, TSS, zones, best
efforts, decoupling), the athlete's FTP/weight/max HR history, `recompute`, and imperial/metric
units. Phase 1c added editing rides (name, notes, effort, bike, tags), bikes with dated
default bikes, and tag/bike/effort filters. Phase 2 added a local web API (`fitlib serve`).
Phase 3a added the browser app (library, ride detail, import) and its Playwright tests;
phase 3b added editing rides, bikes and default bikes, the athlete history, and dark mode.
Phase 4a added route fingerprints and similar rides. **Phase 4b (this)** adds comparing 2 to
4 rides: `fitlib compare`, an API endpoint, and a compare page reached from the library and
from Similar rides.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and, for the browser app, [Node](https://nodejs.org/)
26 (pinned in `.nvmrc`). Python 3.14 is pinned in `.python-version`; uv installs it if needed.

```bash
uv sync                          # create .venv and install dependencies from uv.lock
npm --prefix web ci              # the browser app's dependencies
npm --prefix web run build       # build it into src/fitlib/web_dist/, where fitlib serve finds it
```

## Usage

```bash
uv run fitlib import ~/Documents/Zwift/Activities ~/Downloads/garmin_export.zip
uv run fitlib list                          # newest first
uv run fitlib list --source zwift --since 2025-01-01 --sort power
uv run fitlib list --text "arenberg" --outdoor --min-minutes 60
uv run fitlib show 3f2a9c                   # a ride by id prefix (4+ characters)
uv run fitlib similar 3f2a9c                # rides on the same route
uv run fitlib similar 3f2a9c --effort       # rides with a similar effort
uv run fitlib compare 3f2a9c 7be1 c04d      # 2-4 rides' figures side by side
uv run fitlib show 3f2a9c --units metric    # override the configured units once
uv run fitlib athlete set --from 2025-01-01 --ftp 250 --weight 165 --max-hr 188
uv run fitlib athlete show                  # history, and today's values
uv run fitlib timezone America/New_York     # default time zone (or --clear; none shows it)
uv run fitlib recompute                     # only needed after fitlib's calculations change
uv run fitlib edit 3f2a9c --name "Arenberg" --note "Windy" --rpe 7 --tag z2 --tag cobbles
uv run fitlib edit 3f2a9c 77b0e1 --bike "Giant Contend 1"    # several rides at once
uv run fitlib bikes add "Giant Contend 1" --kind road --default-for outdoor --from 2020-01-01
uv run fitlib bikes default "Tarmac SL7" --for outdoor --from 2023-04-15
uv run fitlib bikes backfill --dry-run      # then without --dry-run
uv run fitlib list --tag z2 --bike giant --min-rpe 6
uv run fitlib --help                        # every command and option
```

- **import** takes folders (searched recursively), `.fit` files and `.zip` archives (Garmin
  Connect's bulk export). Files already imported are recognised by content and skipped, so
  re-running an import, or resuming an interrupted one, is safe. Runs and other non-cycling
  activities are skipped. If a file records the same ride as one already in the library (start
  within 2 minutes, over 80% of the time shared), the ride already there is kept and the file is
  skipped; its original is still archived. Exit code 1 means some files couldn't be read.
- **list** filters by text (name, notes, tags, source, device), dates (UTC), source,
  indoor/outdoor and riding time, and sorts by start, duration, distance or power. It shows
  each ride's TSS; a `*` marks TSS from an estimated FTP.
- **show** prints one ride: local start time, device, times, distance, climbing, speed, power,
  heart rate and cadence; a **Training** block (NP, IF, TSS, VI, work, W/kg, decoupling);
  time in **power zones** (7 Coggan zones) and **heart-rate zones** (5 zones by % of max HR);
  **best efforts** (5 s to 60 min); and laps.
- **similar** lists rides on the same route as a ride, with how much of its route each
  covered ("same" when both cover at least 70 % of each other's, "partly" from 30 %), or with
  `--effort`, the rides with the most similar effort (100 = identical; by length, NP or
  average HR, steadiness and the shape of the power or HR curve, independent of FTP).
- **compare** prints 2 to 4 rides' figures side by side, one column per ride: date, moving
  time, distance, climbing, average speed and power, NP, IF, TSS, average HR, decoupling and
  the best 1, 5 and 20 minutes.
- **athlete** records FTP, weight and max HR from a date on. Each value carries forward until
  changed, so `--ftp 260` alone keeps the earlier weight. Weight is entered and shown in your
  display units and stored in kg. `athlete remove DATE` deletes an entry.
- **timezone** shows or sets the library's default time zone (see "Dates and time zones").
- **edit** sets a ride's name, notes, effort (RPE 1-10), bike and tags; `--clear-…` removes a
  value, `--untag` removes a tag. Effort, bike and tags can be set on several rides at once;
  name and notes only on one. Tags are stored lower-case ("Z2" and "z2" are the same tag).
- **bikes** `add`, `list` (rides, distance and time per bike; `--all` includes retired),
  `rename`, `retire`/`unretire` (a retired bike keeps its rides; bikes are never deleted).
  Quote names with spaces: `"Giant Contend 1"`. Wherever a bike is asked for, its name in any
  case or a unique start of it works (`giant c`).
- **Default bikes** are set per kind of ride (`zwift`, `indoor` for other indoor rides,
  `outdoor`) from a date on, so older rides can have a different bike from newer ones:
  `bikes default NAME --for outdoor --from 2023-04-15`; `--clear` stops defaulting from a
  date; `--remove` deletes an entry; `bikes defaults` shows the timeline. New imports get the
  default for their kind and local date, marked as a default bike (`show` says "(default)").
  `bikes backfill` re-applies the defaults to rides without a bike and to rides whose bike
  came from a default, so adding an older dated default later moves those rides. A bike you
  set with `edit --bike` is never changed.
- **tags** lists tags with their ride counts. `list` filters with `--tag` (repeat to require
  several), `--bike`, `--min-rpe` and `--max-rpe`; text search also matches bike names.
- **recompute** rebuilds rides from their archived original files. It's only needed when
  fitlib's calculations change (`import` says so); by default it updates just the rides that
  need it, or give ride ids or `--all`.

### Browser app

```bash
uv run fitlib serve --open     # http://localhost:8000/ ; --port, --host
```

- **Library** (`/`): search (name, notes, tags, bike, device), filters (source, indoor/outdoor,
  power, dates, minimum riding time, tag, bike, effort), sortable columns and paging. All of it is kept in the
  URL, so reloads, the back button and links keep the view. TSS from an estimated FTP is
  marked with `*`. Tick 2 to 4 rides (from any page or filter; the picks last for the browser
  tab) and press **Compare**.
- **Ride** (`/rides/<id>`): summary and training figures; **Ride Stats**: power, heart rate,
  cadence, speed and altitude stacked on one axis, shown over **time** or **distance**, zoomed
  by dragging the bar's ends or scrolling, and **Show whole ride** to zoom back out; time in
  power and heart-rate zones; best
  efforts; laps. **Edit details** sets the name, notes, effort, bike and tags. **Similar
  rides** lists rides on the same route (newest first, to see progress) and with a similar
  effort, each with a **Compare** link, plus a link comparing the ride with its 3 closest.
- **Compare** (`/compare?ids=a,b,c`): the rides with colour keys (Remove takes one out); their
  figures side by side; Ride Stats (power, heart rate, cadence, speed and altitude overlaid,
  zoomable, with Show whole ride); best efforts overlaid. Rides are lined up by **distance** when they all recorded it, so
  the same point on a route lines up, with a **time gap** chart (how far behind or ahead of
  the first ride each was, stops included), or by **time**. Power and heart rate are smoothed
  over 10 s by default (off or 30 s to choose).
- **Import** (`/import`): choose or drop `.fit` and `.zip` files; the results list what was
  imported (with links), already in the library, skipped and failed.
- **Bikes** (`/bikes`): bikes with their rides, distance and time; add, rename, change kind,
  retire and bring back. The dated default-bike timeline, and applying the defaults to
  existing rides (Preview, then Apply; bikes chosen by hand are never changed).
- **Settings** (`/settings`): the theme, the **Metric units** switch, the default **time
  zone** (a list, or **Use this computer's time zone**; saving says how many rides moved) and
  the athlete history (FTP, weight in your units, max HR from a date on).
- **Light or dark**: one button in the header (and in Settings) showing the mode in use, a sun
  or a moon, named in a hint on hover; clicking switches mode. The theme follows your system
  until you choose; units start from the config. Both choices are remembered in this browser.

The server listens on this computer only (127.0.0.1) and has no login, so don't expose it.
Without a build of `web/` it shows a page saying how to build one.

**Working on the app:** run `uv run fitlib serve` and, in `web/`, `npm run dev` (Vite on
http://localhost:5173/, with `/api` sent to the server). After changing the API, run
`npm run api:types` in `web/` to regenerate `web/src/api/schema.d.ts`; CI fails if it's out of
date.

### Web API

Interactive docs are at `/docs`. Everything is under `/api`, and every figure is in SI units
(metres, seconds, m/s, kg); `GET /api/settings` gives the configured display units.

| Endpoint | What |
|---|---|
| `GET /api/health` | Status, version, ride count and how many rides need `fitlib recompute` |
| `GET /api/rides` | The library: `q` text search, `since`/`until`, `source`, `indoor`, `min_duration_s`/`max_duration_s`, `has_power`, `tag` (repeat for all of several), `bike_id`, `has_bike`, `min_rpe`/`max_rpe`, `sort`, `desc`, `offset`, `limit` (≤ 200) |
| `GET /api/rides/{id}` | One ride (id or 4+ character prefix): summary, training figures, zones, power/HR curves, laps, location box, metadata |
| `GET /api/rides/{id}/similar` | `kind=route` (default): rides covering ≥ 30 % of this ride's route, with `overlap` each way and `same_route`; `kind=effort`: the closest efforts with `similarity` (0–100). `limit` ≤ 50. `has_route` says whether the ride has positions |
| `GET /api/compare` | `ids` (repeat, 2–4, ids or prefixes): each ride's detail and its samples on one shared axis. `align=distance` (metres; with each ride's time `gap` to the first) or `time` (seconds); by default distance when every ride recorded it. `smooth` 0, 10 or 30 s for power and HR; `points` along the axis |
| `GET /api/rides/{id}/streams` | 1 Hz samples as columns; `fields` to choose (lat/lon only when asked for), `step` to thin out |
| `PATCH /api/rides/{id}/meta` | Name, notes, rpe, bike_id, tags. Fields left out stay; `null` clears |
| `GET /api/tags` | Tags with ride counts |
| `GET/POST /api/bikes`, `PATCH /api/bikes/{id}` | Bikes with totals; add; rename, kind, retire |
| `GET /api/bikes/defaults`, `PUT/DELETE /api/bikes/defaults/{slot}/{date}` | Dated default bikes |
| `POST /api/bikes/backfill?dry_run=` | Re-apply default bikes, as `bikes backfill` |
| `GET /api/athlete`, `PUT/DELETE /api/athlete/{date}` | Athlete history and today's values |
| `POST /api/imports` | Upload `.fit`/`.zip` files (multipart `files`); returns what happened to each |
| `GET /api/settings` | Default display units, library folder, default time zone |
| `GET /api/settings/time-zones` | The time zones the default can be set to (IANA names) |
| `PUT /api/settings/timezone` | Set (`{"timezone": "America/New_York"}`) or clear (`null`) the default time zone; returns how many rides changed and how many may need their default bike checked |

Errors are JSON with a `detail` message: 404 for unknown rides or bikes, 409 for ambiguous id
prefixes (with `candidates`) and duplicate bike names, 422 for invalid values.

### Dates and time zones

Dates and times are shown on the rider's clock. A ride's time zone comes from the first of:

1. **The file's own local time** (Garmin devices).
2. **The file's name**, when it is the local start time, as Zwift names files
   (`2026-04-29-07-23-09.fit`). It's used only when it is within 5 minutes of a real time
   zone's reading of the ride's start, so renamed files and wrong clocks are ignored.
   Daylight saving comes out right, as each file has the clock it was ridden on.
3. **The library's default time zone**, set on the Settings page or with `fitlib timezone`.
   It follows daylight saving for each ride's date. Changing it updates the rides that use it
   at once; if a ride moves to another day, its default bike may differ ("Apply defaults to
   existing rides" on the Bikes page brings it in line).
4. Otherwise UTC, marked "UTC".

FTP, weight and default bikes apply by the ride's date on that clock.

Rides you haven't named are named after their source and local start time, so rides on the
same day can be told apart: `Zwift 2026-11-15 07:23`, `Garmin indoor 2025-08-19 20:30`, or
`Ride 2025-08-11 02:00 UTC` for another device with no time zone. Searching finds rides by
these names (e.g. `2026-11-15`).

### Training figures

FTP-based figures (IF, TSS, W/kg, zone times) are **worked out when shown**, from figures
stored per ride (NP, best efforts, seconds at each watt and bpm) and the athlete history in
effect on the ride's date. Changing your FTP history applies everywhere immediately.

For rides before your first FTP entry, FTP is **estimated** as 0.95 × the best 20 minutes in
the six weeks up to the ride, and marked as estimated.

### Configuration

By default the library lives in `~/.fitlib/library`. To change it, create
`~/.fitlib/config.toml` (or point `$FITLIB_CONFIG` or `--config` at another file):

```toml
library = "~/Rides/fitlib"   # relative paths are relative to this file
units = "imperial"           # or "metric"; imperial is the default
```

Units only affect display (mi, mph, ft, lb vs km, km/h, m, kg). Everything is stored in SI
units, as in the FIT files themselves.

### What's stored

```
library/
  catalog.sqlite3                     per ride: summary, laps, best efforts, watt/bpm histograms,
                                      route fingerprint, your notes/tags (searchable); athlete
                                      history
  blobs/raw/<sha[:2]>/<sha>.fit       every original file, unchanged
  blobs/streams/<year>/<id>.parquet   each ride's 1-second samples (zstd Parquet)
```

Ride ids are random. Location (start point and area, and the route fingerprint: the ~150 m
cells a ride passed through) is kept in its own tables, and coordinates are never written to
logs.

**After upgrading** to a version with new calculations, run `fitlib recompute` (the CLI and
the library page say when). Rides imported before phase 4a need it for route matching.
Zwift rides imported before the local-time fix showed the date 30 Dec 1989 (Zwift writes the
FIT epoch as its local time); recompute dates them correctly, falling back to UTC. Zwift
rides imported before the distance fix had no distance (Zwift writes the odometer on only a
few records); recompute adds it up from their speed. Recompute also gives rides imported
before time zones came from file names (Zwift) or the default their local time, and lets
search find rides by their new names (with the start time).

## Code layout

| Module | Role |
|---|---|
| `fitlib/models.py` | Domain objects shared by every layer |
| `fitlib/ingest/` | Find files (incl. zips), decode with `fitdecode`, normalize to 1 Hz, summarize |
| `fitlib/metrics/` | Ride figures from a 1 Hz stream (basic, power, HR, curves, zones), route fingerprints (`route.py`) and FTP-based formulas (`load.py`) |
| `fitlib/analysis/` | FTP-based figures for a ride (athlete history or estimated FTP); default-bike backfill; similar rides (`similar.py`); lining rides up to compare (`compare.py`) |
| `fitlib/metadata.py` | Tag rules, ride kinds for default bikes, and which dated default applies |
| `fitlib/store/` | `CatalogStore` / `BlobStore` interfaces; `local/` (SQLite + files) and `memory/` backends; `factory.py` picks one |
| `fitlib/importer.py` | Hash, dedupe, analyse in worker processes, store |
| `fitlib/recompute.py` | Rebuild rides from their raw files when calculations change |
| `fitlib/api/` | FastAPI app: `app.py` builds it, `routers/` one per area, `schemas.py` request/response models, `errors.py` error responses, `static.py` the browser app's files |
| `fitlib/cli/` | The `fitlib` command: `rides`, `bikes`, `athlete` and `serve` commands, shared `common` helpers and `output` printing |
| `web/` | The browser app (React, Vite, TanStack Query, ECharts): `src/pages/`, `src/components/`, `src/api/` (typed client; `schema.d.ts` is generated), `src/format.ts` (units and figures, as `display.py`) |
| `tests/e2e/` | Playwright tests for the browser app; conventions in `.claude/skills/playwright-tests/` |

Only `store/factory.py` chooses a backend; everything else depends on the interfaces. The API
opens the stores per request. `import-linter` enforces this and the layering
(`models ← metrics ← ingest ← importer | recompute | analysis ← api ← cli`).

**E2E mode** (for the browser tests): with `FITLIB_E2E=1` and `FITLIB_E2E_FIXTURES` pointing
at a fixtures folder, `fitlib serve` adds `/e2e` shortcuts. It only runs over a library inside
the system temp folder, so they can't touch real rides:

| Shortcut | `TestData` | Also tested through the UI by |
|---|---|---|
| `GET /e2e/rides` | `rideIds`, `rideId`, `findRideId` | (read-only) |
| `POST /e2e/rides/{id}/reset-meta` | `resetMeta` | Editing rides (`rideEdits.spec.ts`) |
| `POST /e2e/rides/{id}/delete` | `deleteRide` | Nothing yet: the app can't delete rides |
| `POST /e2e/reset`, `POST /e2e/import/{file}` | (not used yet) | Importing (`import.spec.ts`) |

## Tests

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # formatting (`uv run ruff format .` fixes it)
uv run lint-imports            # module boundaries
uv run pytest                  # every Python test
uv run pytest tests/unit       # or one suite: tests/unit, tests/api

cd web                          # the browser app
npm run lint && npm run typecheck && npm run format:check
npm test                        # unit tests (Vitest)

cd tests/e2e                    # browser tests (first time: npm ci && npx playwright install chromium)
npm run lint && npm run typecheck && npm run format:check
npm test                        # Playwright; starts scripts/e2e-server on port 3200
npm run report                  # the HTML report of the last run
```

- `tests/unit/` covers the Python modules; `tests/api/` drives the web API through FastAPI's
  test client. Both use the synthetic rides in `tests/fixtures/`.
- `web/src/*.test.ts` are Vitest unit tests for the browser app's logic.
- `tests/e2e/` drives the built app in Chromium. `scripts/e2e-server` builds `web/` if its
  sources changed, imports the fixtures into a fresh temp library and serves it in e2e mode.
  Locally Playwright reuses a server that's already running (without re-importing); stop it
  after changing code: `lsof -ti tcp:3200 | xargs kill`.

CI (`.github/workflows/ci.yml`, `e2e.yml`) runs the Python checks, the web app's checks, unit
tests, API types check and build, and the Playwright suite ("Playwright (Chromium)", on pull
requests; the report, traces and screenshots are kept for 7 days when it fails).

Each test has a docstring saying what it checks, with **Given** (inputs) and **Expect**
(outcome); assertions that aren't self-explanatory carry a short failure message.

### Fixtures

All test rides are **synthetic**; no real ride data is committed. They are described in
`tests/fixtures/specs.py` as blocks of constant power, so figures can be checked against values
worked out from the spec. Outdoor rides loop around 50°23′48″N, 3°24′55″E, near Roubaix,
France (one rides its own loop near Ypres); Zwift rides loop around Watopia's coordinates.

The fixtures cover: a steady Zwift ride (written as Zwift writes: named after its local start
time, a 1989 local time inside, the odometer on the first record only), Garmin intervals with a lap per segment, a 10-minute
pause, smart recording (irregular samples), no power meter, an indoor ride without HR or GPS,
a second recording of the Zwift ride, a ride from another maker (Wahoo) with no time zone and
no power or heart rate, a run, two rides inside a `.zip`, an exact duplicate and a truncated
file.

The files in `tests/fixtures/fit/` are generated from the specs and committed. After changing
the specs or the generator, rebuild them:

```bash
uv run python -m tests.fixtures.generate
```

`tests/unit/test_fixtures_current.py` fails if the committed files are out of date.

### What's tested

- **FIT round trip** (`tests/unit/test_fit_roundtrip.py`): rides written with `fit-tool` decode with
  `fitdecode` on Python 3.14 with identical timestamps, power, heart rate, cadence, positions,
  distance, speed, altitude, session and laps; missing channels stay missing; a truncated file
  is rejected. This guards both libraries, neither of which declares Python 3.14 support.
- **Fixtures are current** (`tests/unit/test_fixtures_current.py`).
- **Storage contracts** (`tests/unit/store/`): one suite runs against every catalog (SQLite, memory)
  and blob store (filesystem, memory): round trips, duplicate hashes, id prefixes, time
  windows, every search filter, text search, sorting with missing values last, paging,
  replacing summaries, best efforts in a window, athlete history, editing metadata, bikes
  (unique names ignoring case, name/prefix lookup, renames refreshing search, totals), tag
  counts, default-bike entries and the tag/bike/effort filters, invalid blob keys, Parquet
  streams; library settings; listing rides by where their time zone came from, and changing
  it (name and search follow the new date); plus upgrading a phase 1a database and marking
  existing rides' time zones as from their file.
- **Ingest** (`tests/unit/ingest/`): scanning folders, files and zips (skipping hidden files and
  macOS zip junk); decoding device, sport, local time, records and laps; local times used only
  when real (Zwift's 1989-12-31, seconds since power-on and impossible offsets ignored;
  zones from -12 h to +14 h, to the nearest 15 minutes); rejecting bad files; distance from
  the odometer, or added up from speed when few records carry it (as from Zwift), carrying on
  from the first reading and not growing through pauses; time zones from file names (real
  Zwift names, winter and summer, +5:45, the -12 h and +14 h edges, copies; renamed files,
  impossible dates and offsets no zone has ignored) and the default zone (daylight saving),
  in order after the file's own;
  1 Hz normalization (short gaps filled, pauses kept, duplicate timestamps).
- **Metrics** (`tests/unit/metrics/`): elapsed and moving time, distance, speed, climbing, power,
  heart rate, cadence, location box and laps; NP (against a step-by-step reference), kJ, VI,
  best efforts (incl. never across a pause), decoupling, histograms, zone boundaries, IF/TSS,
  estimated FTP and athlete values carrying forward. Expected values are worked out from the
  specs (e.g. 200 W for an hour at FTP 250 → IF 0.80, TSS 64).
- **Default time zone** (`tests/unit/analysis/test_timezone.py`): only rides without their own
  follow it, with daylight saving; changing and clearing it; an unknown zone changing
  nothing; rides moved to another day with a default bike counted.
- **Training** (`tests/unit/analysis/`): FTP, weight and max HR from the history; estimated FTP
  from the best ride in the window; FTP changes applying without a recompute.
- **Routes and similar rides** (`tests/unit/metrics/test_route.py`,
  `tests/unit/analysis/test_similar.py`): geohash cells against published values,
  neighbours (including across the date line), the fixture loops' fingerprints (same loop
  shares its cells, Watopia none, indoor empty); route matches with GPS drift, partial and
  one-sided overlap, ordering and limits; effort features, the similarity scale, ranking, and
  power rides kept apart from HR-only ones, and a ride with a one-minute stop still a
  similar effort. Import and recompute store fingerprints.
- **Comparing rides** (`tests/unit/analysis/test_compare.py`): lining up by time (rides
  ending early) and by distance (to the shortest ride); the time gap, between whole seconds
  and with a 60 s step at a stop; no distance refused; smoothing that flattens spikes but
  never fills a pause; only recorded channels returned.
- **Metadata** (`tests/unit/test_metadata.py`, `tests/unit/analysis/test_bikes.py`): tag
  normalization; ride kinds; dated default bikes by local date; backfill never overwriting a
  bike set by hand, dry runs, and repeat runs.
- **Recompute** (`tests/unit/test_recompute.py`): outdated rides brought up to date with metadata
  kept; streams rewritten; a Zwift ride dated 1989 repaired (its time zone from its name); a Zwift ride without distance
  given it; missing raw files reported.
- **Importer** (`tests/unit/test_importer.py`): the whole fixture folder (imports, duplicates,
  skips, failures), re-import, stored files and streams, overlapping recordings, the process
  pool, cleanup after a failed write, and no coordinates in logs; time zones from a Zwift
  file's name (also inside a zip) and from the default for a renamed file.
- **CLI** (`tests/unit/test_cli.py`, including `serve` in normal and e2e mode, and `similar`
  by route and effort, with nothing to match, and for rides needing a recompute, and `compare`
side by side, with one ride or the same ride twice refused, and `timezone` shown, set,
cleared and refused for an unknown zone or a zone with `--clear`), **config** and
  **display formatting** (both unit systems).
- **API** (`tests/api/`): the fixture rides are imported once into a template library;
  read-only tests share it and tests that change anything get their own copy. Covered: every
  list filter, sorting and paging, bad parameters; ride detail by id and prefix, ambiguous
  prefixes, training figures with estimated and set FTP, zones and curves; streams (default
  columns, location only on request, thinning, unknown fields); metadata edits (partial,
  clearing, validation leaving the ride unchanged); tags, bikes, default-bike timeline and
  backfill keeping hand-set bikes; athlete history; uploads (`.fit`, `.zip`, duplicates, bad
  and non-FIT files, unsafe file names, default bikes, no coordinates in logs); settings; the
  placeholder page, app-route fallback and 404s for unknown API paths and missing assets;
  `/e2e` shortcuts (including deleting a ride so it can be imported again) only in e2e mode
  and never over a library outside the temp folder; the built app served when present;
  similar rides (the loop's rides as the same route, a partly shared copy, rides without a
  route, effort ranking, bad requests) and the outdated-rides count; comparing (by distance
  by default, by time, four rides by prefix, smoothing, too few or many rides, the same ride
  twice, unknown rides, a ride without distance); the default time zone (zones listed, a ride
  without one moving to the evening before in New York and back to UTC when cleared, rides
  with their own untouched, unknown zones refused).
- **Browser app unit tests** (`web/src/*.test.ts`): durations, distances, speeds, heights and
  weights in both unit systems, and weights typed in either; local versus UTC start times; the
  library's URL state (reading, writing, defaults, every filter, turning it into an API
  query); tag parsing; which theme applies (remembered choice, else the system); picking
  rides to compare (at most four, stored picks read safely) and the compare page's address;
  the stacked charts' spacing and their time (minutes, shown as a clock) and distance axes.
- **Browser tests** (`tests/e2e/`), each written as steps with page objects:
  - *Smoke*: library → open a ride → back → import page → pick two rides and compare them.
  - *Library*: search and an empty result; each filter and filters combined; sorting both ways;
    paging, kept across a reload; the estimated-TSS mark.
  - *Ride detail*: summary, training with an estimated FTP, zones, best efforts, laps and
    charts; a ride without power; a start time without a real local time (UTC; Zwift's 1989 date ignored); switching units,
    remembered across reloads and pages; an unknown ride.
  - *Import*: a new ride imported and opened from the results; duplicates, a run, an
    overlapping recording and a broken file reported.
  - *Ride edits*: every detail edited, shown on the ride and found in the library by name,
    tag, bike and effort; clearing details; a too-long tag refused with nothing saved; Cancel.
  - *Bikes*: add (a duplicate name refused), rename and change kind, retire and bring back;
    the default timeline (set, no bike, remove); Preview and Apply, giving the indoor ride
    its default bike.
  - *Athlete*: save, carry forward, replace and remove values; weight in lb and kg; an empty
    entry refused.
  - *Settings*: the theme button showing the system's mode until clicked, its hover hint,
    switching and staying switched across reloads and pages, header and Settings in sync;
    metric units switched in Settings only and applying everywhere.
  - *Time zone*: choosing New York moves the ride without a time zone to the evening before;
    clearing returns it to UTC; on a computer in Tokyo, one click picks Asia/Tokyo. The Zwift
    ride is dated by its file name (in *Ride detail*).
  - *Similar rides*: the other rides on the loop listed as the same route, newest first, and
    opened; the effort tab reached with the arrow keys, closest first, no HR-only rides; the
    indoor ride (no GPS) and the Zwift ride (alone in Watopia) saying why there's nothing.
  - *Ride stats*: switching the charts between time and distance; the zoom bar's label, and
    Show whole ride enabled once zoomed in and resetting it.
  - *Phone width*: the library, ride and compare pages don't scroll sideways on a 390 px
    screen, and pass the accessibility scan there (wide tables scroll in boxes a keyboard
    can reach).
  - *Compare*: two rides picked in the library and compared (figures side by side, lined
    up by distance with a time gap, zoomed in and back out), picks kept back in the library; four at most, kept while
    filtering, cleared; lining up by time, smoothing off and removing rides down to one;
    comparing from Similar rides, with one ride and with the 3 closest.
  - *Accessibility*: axe WCAG 2.2 AA scans of every page (including Bikes, Settings, the
    ride's edit form, both Similar rides tabs, and the compare page by distance, by time and
    with too few rides) in light mode, dark mode from the system, and dark mode chosen in the
    app.

### Performance check

Not part of CI. Generates synthetic rides over six years, imports them into a temporary
library and times some searches:

```bash
uv run python scripts/perf_import.py --rides 2000
```

## License

[MIT](LICENSE)
