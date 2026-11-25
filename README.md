# Fitlib

A local library for cycling `.fit` files from Zwift and Garmin. It imports rides from folders,
stores them compactly, and summarises each ride in readable numbers, on the command line or in
a browser, finds rides on the same route or with a similar effort, compares rides side
by side, and shows trends: volume, fitness and fatigue, FTP, efficiency and best efforts over
time.

The project is built in phases. Phase 1a added the core: importing, storage, basic ride
figures and a command line. Phase 1b added training figures (NP, IF, TSS, zones, best
efforts, decoupling), the athlete's FTP/weight/max HR history, `recompute`, and imperial/metric
units. Phase 1c added editing rides (name, notes, effort, bike, tags), bikes with dated
default bikes, and tag/bike/effort filters. Phase 2 added a local web API (`fitlib serve`).
Phase 3a added the browser app (library, ride detail, import) and its Playwright tests;
phase 3b added editing rides, bikes and default bikes, the athlete history, and dark mode.
Phase 4a added route fingerprints and similar rides; phase 4b added comparing 2 to 4 rides.
Phase 5a added trends on the command line and in the API: volume per week or month,
fitness/fatigue/form, set and estimated FTP over time, efficiency, best efforts by period, and
progress on a route; phase 5b added them to the browser app. Phase 6a added watched folders:
while `fitlib serve` runs, new rides in folders you choose (such as Zwift's Activities folder)
are imported on their own. **Phase 6b (this)** adds them to the Settings page, with a notice
on every page when new rides arrive.

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
uv run fitlib list --world watopia               # Zwift rides in one world
uv run fitlib show 3f2a9c                   # a ride by id prefix (4+ characters)
uv run fitlib similar 3f2a9c                # rides on the same route
uv run fitlib similar 3f2a9c --effort       # rides with a similar effort
uv run fitlib compare 3f2a9c 7be1 c04d      # 2-4 rides' figures side by side
uv run fitlib progress 3f2a9c               # every ride on this ride's route, oldest first
uv run fitlib trends volume                 # last 12 weeks (--month: 12 months)
uv run fitlib trends fitness                # fitness, fatigue and form, last 90 days
uv run fitlib trends ftp --month            # set and estimated FTP, last year
uv run fitlib trends efficiency             # NP / heart rate per ride, last year
uv run fitlib trends curve --since 2025-01-01   # best power by duration (--hr: heart rate)
uv run fitlib show 3f2a9c --units metric    # override the configured units once
uv run fitlib athlete set --from 2025-01-01 --ftp 250 --weight 165 --max-hr 188 --lthr 165
uv run fitlib athlete born 1980             # threshold heart rate estimated from age
uv run fitlib athlete show                  # history, and today's values
uv run fitlib timezone America/New_York     # default time zone (or --clear; none shows it)
uv run fitlib watch add ~/Documents/Zwift/Activities   # import new rides while serving
uv run fitlib watch list                    # watched folders and the latest files found
uv run fitlib watch scan                    # import what's new in them now
uv run fitlib recompute                     # only needed after fitlib's calculations change
uv run fitlib edit 3f2a9c --name "Arenberg" --note "Windy" --rpe 7 --tag z2 --tag cobbles
uv run fitlib edit 3f2a9c 77b0e1 --bike "Giant Contend 1"    # several rides at once
uv run fitlib delete 3f2a9c 77b0e1          # asks first; --yes doesn't
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
  skipped; its original is still archived. Rides you deleted are skipped too (listed as
  "deleted before"); `--include-deleted` brings them back. Exit code 1 means some files
  couldn't be read.
- **delete** removes rides with their 1-second data and their original files in the library
  (your own copies, in Zwift's or Garmin's folders, are kept). It lists the rides and asks
  first. Their files are remembered, so importing a folder or a Garmin export again doesn't
  bring them back unless asked. Fitness, trends and estimated FTP follow at once.
- **list** filters by text (name, notes, tags, source, device), dates (UTC), source,
  indoor/outdoor and riding time, and sorts by start, duration, distance or power. It shows
  each ride's TSS; `HR` marks TSS from heart rate (rides without power), and a `*` TSS from
  an estimated FTP or threshold heart rate.
- **show** prints one ride: local start time, device, times, distance, climbing, speed, power,
  heart rate and cadence; a **Training** block (NP, IF, TSS, VI, work, W/kg, decoupling, or
  for a ride without power, its TSS from heart rate and the threshold heart rate used);
  time in **power zones** (7 Coggan zones) and **heart-rate zones** (5 zones by % of max HR);
  **best efforts** (5 s to 60 min); and laps.
- **similar** lists rides on the same route as a ride, with how much of its route each
  covered ("same" when both cover at least 70 % of each other's, "partly" from 30 %), or with
  `--effort`, the rides with the most similar effort (100 = identical; by length, NP or
  average HR, steadiness and the shape of the power or HR curve, independent of FTP).
- **compare** prints 2 to 4 rides' figures side by side, one column per ride: date, moving
  time, distance, climbing, average speed and power, NP, IF, TSS, average HR, decoupling and
  the best 1, 5 and 20 minutes.
- **progress** lists every ride on the same route as a ride (both covering at least 70 % of
  each other's), oldest first, with time, distance, speed, power, NP, heart rate and TSS.
- **trends** `volume`, `fitness`, `ftp`, `efficiency` and `curve` (see "Trends"). Each takes
  `--since`/`--until` (local dates); `volume` and `ftp` take `--month`; `fitness` shows each
  Sunday and the last day, or every day with `--daily`; `curve --hr` shows heart rate.
- **athlete** records FTP, weight, max HR and threshold HR (`--lthr`) from a date on. Each
  value carries forward until changed, so `--ftp 260` alone keeps the earlier weight. Weight
  is entered and shown in your display units and stored in kg. `athlete remove DATE` deletes
  an entry. `athlete born YEAR` (or `--clear`) sets the year of birth that threshold heart
  rate is estimated from when none is set.
- **timezone** shows or sets the library's default time zone (see "Dates and time zones").
- **watch** `add FOLDER`, `remove FOLDER`, `list` and `scan`: folders whose new rides are
  imported while `fitlib serve` runs (see "Watched folders"). `scan` imports what's new in
  them now, without the server.
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
uv run fitlib serve --open     # http://localhost:8000/ ; --port, --host, --no-watch
```

- **Library** (`/`): search (name, notes, tags, bike, device), filters (source, indoor/outdoor,
  power, dates, minimum riding time, tag, bike, effort, Zwift world), sortable columns and paging. All of it is kept in the
  URL, so reloads, the back button and links keep the view. TSS from heart rate (rides
  without power) is marked `HR`, and TSS from an estimated FTP or threshold heart rate `*`. Tick rides (from any page or filter, or every ride on a page with the
  header box; the selection lasts for the browser tab, up to 500 rides), then press
  **Compare** (2 to 4 rides), **Edit** to set the effort, bike or tags of them all at
  once (fields left on Keep stay as each ride has them, and tags are added or taken off
  without touching a ride's other tags), or **Delete**, after a confirmation. Name and notes
  are edited on the ride's page. Selected rides deleted elsewhere since (another tab, the
  command line) are unselected when an edit or delete finds them gone, with nothing changed.
- **Ride** (`/rides/<id>`): summary and training figures; **Ride Stats**: power, heart rate,
  cadence, speed and altitude stacked on one axis, shown over **time** or **distance**, zoomed
  by dragging the bar's ends or scrolling, and **Show whole ride** to zoom back out; time in
  power and heart-rate zones; best
  efforts; laps. **Edit details** sets the name, notes, effort, bike and tags; **Delete ride**
  asks, then deletes it and returns to the library. **Similar
  rides** lists rides on the same route (newest first, to see progress) and with a similar
  effort, each with a **Compare** link, plus a link comparing the ride with its 3 closest.
  **Map** (rides with positions): the route with its start (hollow) and finish (filled),
  beside Ride Stats on wide screens. Pointing at Ride Stats puts a dot where you were at
  that moment; zooming Ride Stats highlights that stretch. Outdoor routes are drawn on a plain
  background unless the street map is on (Settings). Zwift routes are always on a plain
  background, named with their world: Zwift's positions aren't real places, and Zwift's own
  map artwork can't be bundled.
  **Progress on this route** charts every ride on the route by date (average speed by
  default, or power, heart rate or moving time), this ride marked, with their table.
- **Trends** (`/trends`): a range (6 weeks, 3 months, 6 months, 1 year, all, or From/To
  dates) and weeks or months, kept in the URL. Summary figures (fitness, fatigue and form on
  the last day, TSS in the range, set and estimated FTP); **Fitness and fatigue** over daily
  TSS, with form below; **Volume** bars (time, distance, climbing, TSS or rides); **FTP**,
  set and estimated; **Efficiency**, a dot per ride (outdoor and indoor) with its 28-day
  average (a dot opens its ride); **Best efforts**, power or heart rate, against the past year
  (by default), all time or the period before. Each chart's numbers are under **Show table**.
  See "Trends" for how each is worked out.
- **Compare** (`/compare?ids=a,b,c`): the rides with colour keys (Remove takes one out); their
  figures side by side; Ride Stats (power, heart rate, cadence, speed and altitude overlaid,
  zoomable, with Show whole ride); best efforts overlaid. Rides are lined up by **distance** when they all recorded it, so
  the same point on a route lines up, with a **time gap** chart (how far behind or ahead of
  the first ride each was, stops included), or by **time**. Power and heart rate are smoothed
  over 10 s by default (off or 30 s to choose). A **Map** overlays the routes in each ride's
  colour: rides in the same place as the first ride with a route (real places, or one Zwift
  world) share it, and the others are listed. A link naming rides deleted since leaves them
  out (the link is rewritten, and the page says how many).
- **Import** (`/import`): choose or drop `.fit` and `.zip` files; the results list what was
  imported (with links), already in the library, skipped and failed, and rides you deleted,
  with **Import them anyway** to bring those back.
- **Bikes** (`/bikes`): bikes with their rides, distance and time; add, rename, change kind,
  retire and bring back. The dated default-bike timeline, and applying the defaults to
  existing rides (Preview, then Apply; bikes chosen by hand are never changed).
- **Settings** (`/settings`): the theme, the **Metric units** switch, the **Street map under
  outdoor routes** switch (off by default; when on, map images load from OpenStreetMap, which
  then sees the areas you look at; remembered in this browser), the default **time
  zone** (a list, or **Use this computer's time zone**; saving says how many rides moved),
  **Watched folders**, the athlete history (FTP, weight in your units, max and threshold
  heart rate from a date on) and the year of birth (today's estimated threshold heart rate is
  shown when none is set). Watched folders: each with its state (watching, not found, can't be watched, or not
  watched with `--no-watch`), the files found and **Stop watching**; a folder added by its
  path (`~` for home), or with one click when Zwift's Activities folder or a Garmin is found
  on this computer; **Scan now**; and the latest files found that weren't already in the
  library, linked to their rides.
- **New rides**: while a page is open, the app checks every 15 s (5 s on Settings; not while
  the tab is hidden) whether the server's watcher has imported rides. If it has, the library,
  trends and ride pages refresh, and a notice says how many arrived, with a link (Dismiss
  hides it).
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
| `GET /api/rides` | The library: `q` text search, `since`/`until`, `source`, `indoor`, `min_duration_s`/`max_duration_s`, `has_power`, `tag` (repeat for all of several), `bike_id`, `has_bike`, `min_rpe`/`max_rpe`, `world` (Zwift rides in one world), `sort`, `desc`, `offset`, `limit` (≤ 200). Each ride says where its time zone came from (`time_zone_source`) and, for Zwift rides, its `zwift_world` |
| `GET /api/zwift-worlds` | The Zwift worlds the `world` filter takes (`slug`, `name`) |
| `GET /api/rides/{id}` | One ride (id or 4+ character prefix): summary, training figures, zones, power/HR curves, laps, location box, metadata |
| `GET /api/rides/{id}/similar` | `kind=route` (default): rides covering ≥ 30 % of this ride's route, with `overlap` each way and `same_route`; `kind=effort`: the closest efforts with `similarity` (0–100). `limit` ≤ 50. `has_route` says whether the ride has positions |
| `GET /api/rides/{id}/route-progress` | Every ride on the same route as this one (itself included), oldest first, as list entries; `has_route` says whether it has positions |
| `GET /api/trends/span` | The first and latest ride's local dates (`null` for an empty library) |
| `GET /api/trends/volume` | `period=week\|month`, `since`/`until` (local dates): rides, `moving_s`, `distance_m`, `ascent_m`, `kj`, `tss` and `rides_without_tss` per week (from Monday) or month, empty ones included |
| `GET /api/trends/fitness` | `since`/`until`: per day `tss`, `fitness` (CTL), `fatigue` (ATL), `form` (TSB); `rides_without_tss` |
| `GET /api/trends/ftp` | `period`, `since`/`until`: per week or month, the set `ftp` and the `estimated` FTP on its last day |
| `GET /api/trends/efficiency` | `since`/`until`: per ride with power and HR (≥ 20 min), `efficiency` (NP / HR), `np`, `avg_hr`, `decoupling_pct`, `indoor` |
| `GET /api/trends/curve` | `kind=power\|hr`, `since`/`until`: the best value at each duration with its `ride_id` and `start` |
| `GET /api/watch` | Watched folders (`state`: watching, missing, error, or stopped with `--no-watch`; `files` found), the latest files that weren't already in the library (`outcome`, `detail`, `ride_id`), files `waiting` to settle, and `last_import` |
| `POST /api/watch/folders`, `DELETE /api/watch/folders?path=` | Watch a folder (`{"path": "~/Documents/Zwift/Activities"}`; 422 for a path that isn't a folder or holds the library, 409 if watched) or stop watching it |
| `POST /api/watch/scan` | Look for new files now: in the background with the watcher running, otherwise before answering, with counts |
| `GET /api/compare` | `ids` (repeat, 2–4, ids or prefixes): each ride's detail and its samples on one shared axis. `align=distance` (metres; with each ride's time `gap` to the first) or `time` (seconds); by default distance when every ride recorded it. `smooth` 0, 10 or 30 s for power and HR; `points` along the axis |
| `GET /api/rides/{id}/streams` | 1 Hz samples as columns; `fields` to choose (lat/lon only when asked for), `step` to thin out |
| `PATCH /api/rides/{id}/meta` | Name, notes, rpe, bike_id, tags. Fields left out stay; `null` clears |
| `POST /api/rides/bulk-meta` | `ids` (1–500, ids or prefixes) plus rpe, bike_id, add_tags, remove_tags for all of them: fields left out stay, `null` clears. All the rides change or none (an unknown ride or bike is a 404); returns `updated` |
| `GET /api/tags` | Tags with ride counts |
| `GET/POST /api/bikes`, `PATCH /api/bikes/{id}` | Bikes with totals; add; rename, kind, retire |
| `GET /api/bikes/defaults`, `PUT/DELETE /api/bikes/defaults/{slot}/{date}` | Dated default bikes |
| `POST /api/bikes/backfill?dry_run=` | Re-apply default bikes, as `bikes backfill` |
| `GET /api/athlete`, `PUT/DELETE /api/athlete/{date}` | Athlete history (FTP, weight, max and threshold HR), today's values, the year of birth and today's threshold estimated from it |
| `PUT /api/athlete/birth-year` | `birth_year` (1900 to this year, or `null` to clear) |
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

The ride page (and `fitlib show`) says which of these a ride's time came from, with a link to
Settings when it's the default or UTC; the library marks UTC dates.

FTP, weight and default bikes apply by the ride's date on that clock.

### Zwift worlds

Zwift records positions on Earth: London, New York, Paris and the other city worlds sit on the
real city, and the made-up ones on small Pacific islands (Watopia on Teanu, in the Solomon
Islands). A Zwift ride's **world** is the one whose area holds its start point, from the
world areas in [zwift-data](https://github.com/andipaetzold/zwift-data) (MIT). It shows on
the ride page, in the library's Source column ("Zwift (Watopia)") and in `fitlib show`, and
the library's **World** filter (`fitlib list --world`) finds a world's rides. Zwift's route
names aren't shown: no public data has the routes' paths to match a ride to.

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

Rides **without power** get a TSS from heart rate: each riding second adds
(heart rate ÷ threshold heart rate)², and an hour at threshold scores 100, as an hour at FTP
does. It's worked out from the seconds stored at each bpm, so it needs no recompute. The
threshold heart rate is the first of:

1. The one **set** in the athlete history on the ride's date.
2. **From your rides**: the FTP on that day (set or estimated) times your heart rate per
   watt, √(Σ seconds × HR² ÷ Σ seconds × NP²), over your rides with power and heart rate of
   20 minutes or more in the 90 days up to it (at least 3 of them). This is the threshold at
   which those rides' heart-rate TSS adds up to their power TSS, so rides with and without
   power count on the same scale.
3. **Estimated from your age** that year: 90 % of 208 − 0.7 × age (Tanaka's age-predicted
   maximum).

The ride page says which ("from your rides", "estimated from age"), and a TSS from a threshold
that wasn't set is starred. With none of them, the ride has no TSS. Rides with power always use
power TSS (heart rate is used only when there's no FTP to compare with).

### Trends

Trends use the figures stored per ride, never the 1 Hz samples, so they're quick over years
of rides. Rides count on their **local date**; date ranges are local dates, both ends
included. Left out, a range ends today.

- **Volume**: rides, moving time, distance, climbing, work (kJ) and TSS per week (Monday to
  Sunday) or month. The first week or month is widened back to its start; empty ones show as
  zeros. Default: 12 weeks or 12 months.
- **Fitness, fatigue and form**: fitness (CTL) is an exponentially weighted average of daily
  TSS over 42 days, fatigue (ATL) over 7 days, and form (TSB) is yesterday's fitness minus
  fatigue. They're built up from your first ride, so a day's values don't depend on the range
  shown. Default: 90 days.
- **TSS** is the same as on each ride: from power and the FTP set on its date, or estimated;
  for rides without power, from heart rate. Rides with neither add 0 and are counted, so you
  can see what's missing.
- **FTP over time**: at the end of each week or month, the FTP set in the athlete history and
  the estimate (0.95 × the best 20 minutes in the six weeks up to that day). Default: a year.
- **Efficiency**: Normalized Power / average heart rate (W per bpm) for each ride with power
  and heart rate lasting at least 20 minutes; higher means more power for the same heart
  rate. Shown with the ride's decoupling. Default: a year.
- **Best efforts by period**: the best power or heart rate at each duration from 1 s to 2 h,
  with the ride each came from. Default: 42 days.
- **Route progress**: every ride on the same route as a ride, oldest first.

### Configuration

By default the library lives in `~/.fitlib/library`. To change it, create
`~/.fitlib/config.toml` (or point `$FITLIB_CONFIG` or `--config` at another file):

```toml
library = "~/Rides/fitlib"   # relative paths are relative to this file
units = "imperial"           # or "metric"; imperial is the default
```

Units only affect display (mi, mph, ft, lb vs km, km/h, m, kg). Everything is stored in SI
units, as in the FIT files themselves.

### Watched folders

While `fitlib serve` runs, it watches the folders added with `fitlib watch add` (or the API)
and imports new `.fit` and `.zip` files in them, searched recursively, as for `import`:

- A file is imported once it has stopped changing for 10 seconds, so a ride still being
  written isn't read half done. Zwift's `inProgressActivity.fit` (rewritten all through a
  ride) and hidden files are ignored.
- When the server starts, and every 10 minutes, each folder is scanned for files added while
  nothing was watching. Files already imported with the same size and modification time are
  passed over without being read, so the scans stay quick; the first scan of a folder you
  had already imported reads each file once and finds it already in the library.
- A file that couldn't be read is tried again once it changes. A folder that disappears (an
  unplugged Garmin at `/Volumes/GARMIN/...`, or a renamed folder) is shown as missing and
  watched again when it comes back. Folders added from the command line are picked up within
  30 seconds.
- The library folder, folders inside it and folders holding it can't be watched (its archive
  holds `.fit` files). `fitlib serve --no-watch` serves without watching.
- Watched folders and the files found in them are stored in the library but belong to this
  computer: their paths mean nothing elsewhere.

On a Mac, watching a folder in Documents needs the same permission (Files and Folders) as
importing from it.

### Encrypted backup (optional)

Nothing leaves this computer unless you set this up. `fitlib sync` keeps an encrypted copy of
the library in a folder you choose, typically a USB drive or NAS (a cloud-synced folder works
too). Everything is encrypted on this computer before it is written there; reading, search
and analysis stay local. The same encrypted format is the groundwork for a possible web
version later.

```bash
mkdir -p ~/Library/Mobile\ Documents/com~apple~CloudDocs/fitlib
fitlib sync setup ~/Library/Mobile\ Documents/com~apple~CloudDocs/fitlib   # asks for a passphrase
fitlib sync push            # uploads what changed
fitlib sync status          # the latest copy, and what a push would upload
fitlib sync passphrase      # change the passphrase

# On another computer, with `library` in its config pointing at an empty folder:
fitlib sync restore ~/Library/Mobile\ Documents/com~apple~CloudDocs/fitlib
```

- **Keys.** Each library has a random 256-bit key, kept in the macOS Keychain. The sync
  folder's `keyfile` holds a copy encrypted with your passphrase (Argon2id, 64 MiB), so a new
  computer needs only the folder and the passphrase. fitlib can't recover the passphrase: if
  you lose it and every computer's Keychain copy, the sync folder can't be read.
- **What the folder shows.** `keyfile`, `manifest` and files named
  `objects/<2 hex>/<64 hex>`. Names are keyed hashes, so they don't reveal dates, ride ids or
  file hashes. Each object is AES-256-GCM encrypted and bound to its place in the library, so
  objects can't be swapped or edited without restore noticing. Original files and the
  catalog are compressed first. Sizes are not hidden.
- **What's copied.** Original files, streams and a snapshot of the catalog (rides, your
  notes, tags, bikes, athlete history, settings). Watched folders and sync settings belong to
  this computer and stay behind.
- **Pushing.** Only changed files are uploaded. Writing the manifest is the last step, so an
  interrupted push leaves the previous copy whole; objects no longer needed are removed after
  it. One computer pushes at a time: if another pushed since this library last pushed or
  restored, `push` stops and `--force` replaces that copy.
- **Restoring** only writes into an empty library, checks every object against the manifest,
  and writes the catalog last, so an interrupted restore can be run again. A copy from a
  newer fitlib is refused.

### Security on this computer

fitlib has no login: it's meant for the account that runs it.

- `fitlib serve` listens on 127.0.0.1 only, so other computers can't reach it (`--host`
  can change that, with a warning).
- Web pages in your own browser can send requests to `localhost`, so the server also checks
  where requests come from:
  - It only answers requests addressed to `localhost`, `127.0.0.1` or `[::1]`, so a site
    that points its own domain at your computer ("DNS rebinding") can't read the library.
  - Anything that changes the library (POST, PUT, PATCH, DELETE) is only accepted from
    fitlib's own pages: a browser's `Origin` must match, and a `Sec-Fetch-Site` naming
    another site is refused. The command line, scripts and `curl` send neither and work as
    before.
- Every response tells the browser not to embed it in other sites, not to guess file types,
  not to send referrers, and (Content-Security-Policy) to run only fitlib's own scripts and
  talk only to fitlib. The one outside source allowed is OpenStreetMap's map images, which
  load only when the street map is switched on; those requests send the page's origin
  (`http://localhost:8000`) as their referrer, as OpenStreetMap asks of web pages, and
  nothing else. The API docs at `/docs` load from a CDN, so they go without the policy.
- The library folder is readable only by your account (mode 700). Existing libraries are
  tightened the next time they're opened.

### What's stored

```
library/
  catalog.sqlite3                     per ride: summary, laps, best efforts, watt/bpm histograms,
                                      route fingerprint, your notes/tags (searchable); athlete
                                      history; hashes of deleted rides' files
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
| `fitlib/metrics/` | Ride figures from a 1 Hz stream (basic, power, HR, curves, zones), route fingerprints (`route.py`), simplified tracks for maps (`track.py`) and FTP-based formulas (`load.py`) |
| `fitlib/analysis/` | FTP-based figures for a ride (athlete history or estimated FTP); similar rides (`similar.py`); lining rides up to compare (`compare.py`); trends over many rides (`trends.py`) |
| `fitlib/metadata.py` | Tag rules, ride kinds for default bikes, and which dated default applies |
| `fitlib/store/` | `CatalogStore` (the sum of its roles `RideCatalog`, `BikeCatalog`, `AthleteCatalog`, `SettingsStore` and `WatchState`; functions take the role they need) / `BlobStore` interfaces; `local/` (SQLite + files) and `memory/` backends, each catalog a package with a `base.py` and one file per role; `factory.py` picks one; `settings.py` declares each library setting once, with its type and whether it stays on this computer |
| `fitlib/services/` | The tasks the browser app and the command line share: `rides.py` (finding, listing, samples, maps, similar rides, route progress, editing, deleting), `compare.py`, `bikes.py` (bikes, the default timeline and backfill), `athlete.py`, `importing.py` (hash, dedupe, analyse in worker processes, store), `recompute.py` (rebuild rides from their raw files when calculations change), `deleting.py` (rides with their streams and original files), `watching.py` (watched folders: which files, settling, scans, and the background watcher the server runs); `context.py` loads the athlete's values and the bikes once for showing many rides; `errors.py` the requests a person can fix |
| `fitlib/sync/` | Optional encrypted backup: `crypto.py` (sealed objects, object names, the passphrase keyfile), `keys.py` (Keychain), `engine.py` (setup, push, status, restore) |
| `fitlib/api/` | FastAPI app: `app.py` builds it, `routers/` one per area (endpoints only), `schemas/` the request/response models and the code building them, one module per router, `errors.py` error responses, `security.py` refusing other sites and adding security headers, `static.py` the browser app's files |
| `fitlib/cli/` | The `fitlib` command: `rides`, `bikes`, `athlete`, `timezone`, `trends`, `watch`, `sync` and `serve` commands, shared `common` helpers and `output` printing |
| `web/` | The browser app (React, Vite, TanStack Query, ECharts, Leaflet for maps): one folder per feature in `src/` holding its page and components (`library/`, `ride/`, `compare/`, `trends/`, `map/`, `bikes/`, `settings/`, `imports/`), the shell in `app/`, shared parts in `shared/` (e.g. `format.ts`, units and figures as `display.py`) and `charts/`, and `src/api/` (`client.ts` for requests and errors, one module of types and hooks per resource; `schema.d.ts` is generated). ESLint keeps `api/`, `shared/` and `charts/` from importing a feature |
| `tests/e2e/` | Playwright tests for the browser app; conventions in `.claude/skills/playwright-tests/` |

Only `store/factory.py` chooses a backend; everything else depends on the interfaces. The API
opens the stores per request. API routers and CLI commands read their input, call a service and
show the result; the work itself is in `services/`, so both behave the same. `import-linter`
enforces this and the layering
(`models ← metrics ← ingest ← analysis | sync ← services ← api ← cli`, and inside services
`errors ← importing | recompute | deleting | context ← rides | bikes | athlete | watching ← compare`;
sync gets the catalog snapshot through the factory, never SQLite itself; the API and CLI import
only names such as types and constants from `metrics` and `ingest`).

**E2E mode** (for the browser tests): with `FITLIB_E2E=1` and `FITLIB_E2E_FIXTURES` pointing
at a fixtures folder, `fitlib serve` adds `/e2e` shortcuts. It only runs over a library inside
the system temp folder, so they can't touch real rides:

| Shortcut | `TestData` | Also tested through the UI by |
|---|---|---|
| `GET /e2e/rides` | `rideIds`, `rideId`, `findRideId` | (read-only) |
| `POST /e2e/rides/{id}/reset-meta` | `resetMeta` | Editing rides (`rideEdits.spec.ts`) |
| `POST /e2e/rides/{id}/delete` | `deleteRide` (doesn't remember the file as deleted) | Deleting rides (`rideDelete.spec.ts`) |
| `POST /e2e/reset`, `POST /e2e/import/{file}` | (not used yet) | Importing (`import.spec.ts`) |
| `POST /api/imports` | `importFile` (extra rides kept out of the library at start-up) | Importing (`import.spec.ts`) |
| `GET /api/watch`, `DELETE /api/watch/folders` | `stopWatchingLeftovers` (folders a failed run left) | Watched folders (`watchedFolders.spec.ts`) |

In e2e mode, only folders inside the temp folder can be watched, and no folders are suggested.

## Tests

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # formatting (`uv run ruff format .` fixes it)
uv run lint-imports            # module boundaries
uv run mypy                    # types (src, tests and scripts)
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
- `web/src/**/*.test.ts` are Vitest unit tests for the browser app's logic, next to the module each tests.
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
file. Four more rides, outdoor near Arras with heart rate only (3, 4, 7 and 8 Aug), are kept
in `tests/fixtures/extra/` rather than the fixture folder, so they're never in the library at
the start: the browser tests drop one into a watched folder, edit two together and delete one.

The files in `tests/fixtures/fit/` are generated from the specs and committed. After changing
the specs or the generator, rebuild them:

```bash
uv run python -m tests.fixtures.generate
```

`tests/unit/test_fixtures_current.py` fails if the committed files (in both folders) are out of
date.

### What's tested

- **FIT round trip** (`tests/unit/test_fit_roundtrip.py`): rides written with `fit-tool` decode with
  `fitdecode` on Python 3.14 with identical timestamps, power, heart rate, cadence, positions,
  distance, speed, altitude, session and laps; missing channels stay missing; a truncated file
  is rejected. This guards both libraries, neither of which declares Python 3.14 support.
- **Fixtures are current** (`tests/unit/test_fixtures_current.py`).
- **Settings** (`tests/unit/store/test_settings.py`): values back with their types (and as
  stored by earlier versions), clearing, the machine-local settings being exactly the sync
  ones, and no raw setting reads or writes outside the store.
- **Storage contracts** (`tests/unit/store/`, the catalog's in `tests/unit/store/catalog/`, one file per role): one suite runs against every catalog (SQLite, memory)
  and blob store (filesystem, memory): each catalog playing every role, round trips, duplicate hashes, id prefixes, time
  windows, every search filter (including where a ride starts), text search, sorting with missing values last, paging,
  replacing summaries, trend rows (with each ride's heart rate squared, summed,
  for heart-rate TSS), athlete history, editing metadata (one ride,
  or several at once with nothing changed if one fails), bikes
  (unique names ignoring case, name/prefix lookup, renames refreshing search, totals), tag
  counts, default-bike entries and the tag/bike/effort filters, invalid blob keys, Parquet
  streams; library settings; listing rides by where their time zone came from, and changing
  it (name and search follow the new date); plus upgrading a phase 1a database, marking
  existing rides' time zones as from their file, and keeping athlete entries when threshold
  heart rate is added.
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
  TSS from heart rate (an hour at threshold scoring 100, mixed rides summing their parts,
  power preferred), heart rate per watt over 90 days once there are 3 rides (short, old and
  power-less rides left out), threshold heart rate estimated from age, estimated FTP and athlete
  values carrying forward. Expected values are worked out from the
  specs (e.g. 200 W for an hour at FTP 250 → IF 0.80, TSS 64).
- **Default time zone** (`tests/unit/analysis/test_timezone.py`): only rides without their own
  follow it, with daylight saving; changing and clearing it; an unknown zone changing
  nothing; rides moved to another day with a default bike counted.
- **Training** (`tests/unit/analysis/`): FTP, weight and max HR from the history; estimated FTP
  from the best ride in the window (both ends of the six weeks included, matching a brute
  force over every fixture ride's stored curve); FTP changes applying without a recompute; a ride without
  power getting TSS from a set threshold heart rate or one estimated from age (a set one
  winning); power TSS kept for rides with power; impossible years of birth refused; the
  threshold from your rides (making heart-rate TSS equal power TSS on them, using the set or
  estimated FTP, needing 3 recent rides, a set threshold winning) and today's threshold.
- **Zwift worlds** (`tests/unit/metrics/test_zwift.py`): each world's centre and corners
  found as that world, no two worlds overlapping, real rides and points just outside a world
  in none, only Zwift rides with positions having a world, worlds by name.
- **Maps** (`tests/unit/metrics/test_track.py`, `tests/api/test_map.py`): a straight road
  kept as its two ends, wobble within 3 m dropped and corners kept, a closed loop keeping its
  shape, a wiggly track capped at its point limit with its ends, a fixture loop inside its
  bounds with rising distances and the right start-to-finish gap, no track without positions
  and none without distance; the API's route for an outdoor ride, a Zwift ride (named world),
  an indoor ride (empty) and an unknown ride (404).
- **Routes and similar rides** (`tests/unit/metrics/test_route.py`,
  `tests/unit/analysis/test_similar.py`): geohash cells against published values,
  neighbours (including across the date line), the fixture loops' fingerprints (same loop
  shares its cells, Watopia none, indoor empty); route matches with GPS drift, partial and
  one-sided overlap, ordering and limits; effort features, the similarity scale, ranking, and
  power rides kept apart from HR-only ones, and a ride with a one-minute stop still a
  similar effort. Import and recompute store fingerprints.
- **Trends** (`tests/unit/analysis/test_trends.py`): TSS equal to the ride page's for every
  fixture ride, with set and estimated FTP and from heart rate; rides without power adding
  heart-rate TSS to volume and fitness; including estimates looking back before the
  range; volume by week and month by local date (a ride late on Sunday UTC counted on Monday,
  empty weeks as zeros); fitness, fatigue and form by hand and independent of the range;
  FTP per week and month, and an estimate expiring after six weeks; efficiency only for rides
  with power, heart rate and 20 minutes; best efforts leaving out rides outside the range by
  local date; route progress; an empty library; default ranges and a backwards range refused.
  The store's trend rows and best curve by period are in the catalog contract tests.
- **Comparing rides** (`tests/unit/analysis/test_compare.py`): lining up by time (rides
  ending early) and by distance (to the shortest ride); the time gap, between whole seconds
  and with a 60 s step at a stop; no distance refused; smoothing that flattens spikes but
  never fills a pause; only recorded channels returned.
- **Deleting rides** (`tests/unit/services/test_deleting.py`, `tests/api/test_delete.py`, catalog
  contract and CLI tests): the ride, its stream and original file gone, others untouched;
  several at once all or none (an unknown id deletes nothing); deleted files remembered and
  skipped on re-import (alone or inside a zip), `include_deleted` / `--include-deleted`
  bringing them back for good, test set-up deletes not remembered; the API's single and bulk
  delete (1 to 500 rides, repeats counted once, 404 for unknown rides with a readable
  message); compare, bulk edit and bulk delete listing every missing ride at once
  (`missing`, in `tests/api/test_missing.py`) and changing nothing; recent watched-folder files marked when their ride is deleted; `fitlib delete`
  asking, `--yes`, unknown rides; the watcher reporting deleted files as skipped.
- **Metadata** (`tests/unit/test_metadata.py`, `tests/unit/services/test_backfill.py`): tag
  normalization; edits (kept, set and cleared fields, tags added and removed, a bike chosen
  by hand); ride kinds; dated default bikes by local date; backfill never overwriting a
  bike set by hand, dry runs, and repeat runs.
- **Services** (`tests/unit/services/`): a list of rides loading the athlete's values and the
  bikes once (with the same figures as one ride on its own), and making the same queries for
  one ride as for eight (estimated FTPs come from the loaded profile); every missing ride named at
  once; the Zwift world filter and its errors; sample columns (positions only when asked,
  unknown ones refused); matches by route and by effort; editing and deleting all or nothing,
  each ride once; compare's checks (2 to 4 rides, no repeats, offered smoothing, distance only
  when every ride has it); bike names tidied, partial bike changes, the default timeline;
  the athlete today; removing entries that aren't there.
- **Recompute** (`tests/unit/services/test_recompute.py`): outdated rides brought up to date with metadata
  kept; streams rewritten; a Zwift ride dated 1989 repaired (its time zone from its name); a Zwift ride without distance
  given it; missing raw files reported.
- **Encrypted backup** (`tests/unit/sync/`, `tests/unit/store/test_snapshot.py`): sealed objects
  round trip; a changed byte in any part, another key, or another object's place refused;
  object names stable and revealing nothing; the keyfile opening only with its passphrase,
  its settings authenticated, short passphrases refused. Push then restore giving the same
  rides, metadata and files byte for byte, without watched folders; the folder listing only
  opaque names; **no plaintext in any byte of the folder** (ride ids, file hashes, notes,
  tags, devices, file names, the SQLite and Parquet headers, each ride's first GPS point as
  float64, float32 and FIT semicircles); second pushes uploading only changes; a push failing
  part way keeping the last copy; another computer's push needing `--force`; a tampered or
  swapped object, a newer schema and a wrong passphrase stopping a restore before the catalog
  is written; status; passphrase changes; no ride details in the logs. Snapshots leave out
  this computer's data and are byte-identical when nothing changed. The commands run end to
  end with an in-memory keychain; the Keychain store against a stand-in keyring backend.
- **Security** (`tests/api/test_security.py`, `tests/unit/store/test_private_library.py`):
  loopback hosts answered and other hosts (DNS rebinding) refused on pages and API; writes
  of every method and multipart uploads from another site, another port, `Origin: null` or a
  cross-site `Sec-Fetch-Site` refused with nothing changed; the app's own pages, same-origin
  and typed-in requests, and tools without browser headers accepted; reads sent without
  CORS permission; security headers on pages, API answers, errors and refusals, and no CSP
  on the API docs; any host answered (writes still checked) when serving on a network
  address; `fitlib serve` refusing other hosts by default. Library folders created or
  tightened to 0700, including by restore.
- **Watched folders** (`tests/unit/services/test_watching.py`): which folders can be watched (full
  paths, `~`, not the library or near it, inside the temp folder in e2e mode); which files
  (`.fit`/`.zip`, not Zwift's in-progress file or hidden ones); summing up a file's or a zip's
  import; scans importing new files once, retrying a failed file once it changes, leaving
  files still being written; the watcher step by step with a fake clock (catching up, waiting
  for a file to settle, idle passes leaving the library closed, deleted files, a folder
  missing then back, folders added and removed, scans on request and every 10 minutes); and
  with the real file watcher, a dropped-in ride imported, also after a restart. The store's
  watched folders and files are in the catalog contract tests, with opening a new library
  from several threads at once.
- **Importer** (`tests/unit/services/test_importing.py`): the whole fixture folder (imports, duplicates,
  skips, failures), re-import, stored files and streams, overlapping recordings, the process
  pool, cleanup after a failed write, and no coordinates in logs; time zones from a Zwift
  file's name (also inside a zip) and from the default for a renamed file.
- **CLI** (`tests/unit/test_cli.py`, including `serve` in normal and e2e mode, and `similar`
  by route and effort, with nothing to match, and for rides needing a recompute, and `compare`
side by side, with one ride or the same ride twice refused, `show` naming the Zwift world
and where the time came from (device, file name, UTC, the default), `list --world` (unknown
worlds and other sources refused), and `timezone` shown, set,
cleared and refused for an unknown zone or a zone with `--clear`, every `trends` view, a
backwards range and an empty period, `progress` on the loop, alone and without GPS, `serve`
with and without `--no-watch`, and `watch` add, scan, list and remove, refusals, files still
being written, and nothing watched),
**config** and
  **display formatting** (both unit systems).
- **API** (`tests/api/`): the fixture rides are imported once into a template library;
  read-only tests share it and tests that change anything get their own copy. Covered: every
  list filter, sorting and paging, bad parameters; the world filter (unknown worlds and other
  sources refused) and the worlds list; where each ride's time zone came from; ride detail by id and prefix, ambiguous
  prefixes, training figures with estimated and set FTP, zones and curves; streams (default
  columns, location only on request, thinning, unknown fields); metadata edits (partial,
  clearing, validation leaving the ride unchanged), and of several rides at once (repeats
  counted once, the name left alone, bad values or an unknown ride changing nothing); tags, bikes, default-bike timeline and
  backfill keeping hand-set bikes; athlete history (with threshold heart rate), the year of
  birth and its estimate, impossible years refused, heart-rate TSS on rides and the
  library list, and the threshold from your rides ahead of the age (on a ride, and today's
  from age with no recent rides); uploads (`.fit`, `.zip`, duplicates, bad
  and non-FIT files, unsafe file names, default bikes, no coordinates in logs); settings; the
  placeholder page, app-route fallback and 404s for unknown API paths and missing assets;
  `/e2e` shortcuts (including deleting a ride so it can be imported again) only in e2e mode
  and never over a library outside the temp folder; the built app served when present;
  similar rides (the loop's rides as the same route, a partly shared copy, rides without a
  route, effort ranking, bad requests) and the outdated-rides count; comparing (by distance
  by default, by time, four rides by prefix, smoothing, too few or many rides, the same ride
  twice, unknown rides, a ride without distance); the default time zone (zones listed, a ride
  without one moving to the evening before in New York and back to UTC when cleared, rides
  with their own untouched, unknown zones refused); trends (the span, weekly and monthly
  volume adding up to the rides, default ranges, fitness from the Zwift ride, FTP before and
  after setting one, efficiency, best efforts naming their rides, an empty period, backwards
  ranges refused); watched folders (added as typed, listed, removed, refusals, a missing
  folder, Zwift's folder suggested until it's watched, a scan without the watcher, the server's watcher importing a new folder's ride and
  then one copied in, and e2e mode keeping to the temp folder) and route progress (the loop
  oldest first, rides alone or without GPS,
  unknown rides).
- **Browser app unit tests** (`web/src/**/*.test.ts`): durations, distances, speeds, heights and
  weights in both unit systems, and weights typed in either; local versus UTC start times; the
  library's URL state (reading, writing, defaults, every filter, turning it into an API
  query, the World filter dropping another source and the other way round); where a ride's
  time zone came from, in words; tag parsing; which theme applies (remembered choice, else the system); picking
  rides to compare or edit (up to 500, a whole page at once, stored selections read safely),
  what the bulk edit form sends, and the compare page's address; the trends summary
  (the last day's fitness, fatigue and form, total TSS, FTP at the end, dashes with no data);
  what the athlete form saves (blank fields left out, pounds to kilograms, a date and a value
  needed);
  the stacked charts' spacing and their time (minutes, shown as a clock) and distance axes;
  the trends page's URL state, preset and custom ranges, the comparison ranges for best
  efforts, the 28-day average, volume figures in both unit systems, and date labels; moments
  shown on this computer's clock.
- **Browser tests** (`tests/e2e/`), each written as steps with page objects:
  - *Smoke*: library → open a ride → back → import page → pick two rides and compare them →
    trends over all the rides.
  - *Trends* (18 to 31 Aug 2025, rides no other spec changes): the range from the URL;
    estimated FTP; volume by week as a table, distance instead of time, by month; FTP each
    Sunday; efficiency of the rides with heart rate, opening one; fitness's table with that
    day's TSS; best power against the past year and the period before (with the difference),
    heart rate, opening the ride behind a best and back with choices kept; a preset from the
    header ending today, kept across a reload; a backwards range refused.
  - *Library*: search and an empty result; each filter and filters combined; sorting both ways;
    paging, kept across a reload; the estimated-TSS mark; the World filter (Watopia finding
    the Zwift ride, shown as "Zwift (Watopia)", London nothing, Garmin clearing the world).
  - *Ride detail*: summary, training with an estimated FTP, zones, best efforts, laps and
    charts; a ride without power (only TSS from heart rate and the threshold from your rides); a start time without a real local time (UTC; Zwift's 1989 date ignored); switching units,
    remembered across reloads and pages; an unknown ride; where the start time came from (the
    device, or the Zwift ride's file name), and the Zwift ride's world.
  - *Import*: a new ride imported and opened from the results; duplicates, a run, an
    overlapping recording and a broken file reported.
  - *Ride edits*: every detail edited, shown on the ride and found in the library by name,
    tag, bike and effort; clearing details; a too-long tag refused with nothing saved; Cancel.
  - *Maps*: an outdoor ride's route on a plain background, named with its distance and
    start-to-finish gap, pointing at Ride Stats putting a dot on it and zooming highlighting
    a stretch (cleared by Show whole ride), no map images loaded, accessibility scans in light
    and dark. The street map switched on in Settings: map images under an outdoor route
    (answered by the test, never fetched) with OpenStreetMap's credit; none for the Zwift
    ride, drawn on a plain background as Watopia; switched off and kept off across a reload.
    No map for the indoor ride. Compare: two outdoor routes sharing a map, the Zwift and
    indoor rides listed, an accessibility scan.
  - *Rides that are gone* (an id no ride has, standing for one deleted since; nothing is
    changed): a compare link naming it compares the other two and says one was left out (no
    longer in the link); with one ride left, the page asks for more. A selection holding it:
    an edit unselects it and changes nothing, and deleting a selection of only that ride
    unselects it and deletes nothing.
  - *Deleting rides* (an extra ride on 8 Aug, imported by the spec): asking from its page,
    Cancel focused, cancelling with the button and with Escape, an accessibility scan of the
    dialog; deleting, back in the library with "Deleted …" (not again after a reload), the
    ride gone and its page not found; importing its file again leaving it out as deleted before, and **Import them
    anyway** bringing it back. Deleting it from the library's selection: "Delete 1 ride",
    gone, unselected and "Deleted 1 ride.".
  - *Bulk edits* (two extra rides on 3 and 4 Aug, imported by the spec): both selected with
    the page checkbox and given an effort, a new bike and two tags; one unselected (the page
    box part-ticked), the other's effort cleared and a tag taken off; the library's filters
    finding the edits; Close and Clear selection. A too-long tag refused with neither ride
    changed. An accessibility scan with the form open.
  - *Bikes*: add (a duplicate name refused), rename and change kind, retire and bring back;
    the default timeline (set, no bike, remove); Preview and Apply, giving the indoor ride
    its default bike.
  - *Athlete*: save (including threshold heart rate), carry forward, replace and remove
    values; weight in lb and kg; an empty entry refused. A year of birth (this year, so no
    fixture ride changes) saved with its estimate, kept across a reload, 1899 refused, and
    cleared.
  - *Settings*: the theme button showing the system's mode until clicked, its hover hint,
    switching and staying switched across reloads and pages, header and Settings in sync;
    metric units switched in Settings only and applying everywhere.
  - *Time zone*: the ride without a time zone said to be in UTC, marked UTC in the library;
    choosing New York moves it to the evening before, said to be the default, with the link to
    Settings; clearing returns it to UTC; on a computer in Tokyo, one click picks Asia/Tokyo. The Zwift
    ride is dated by its file name (in *Ride detail*).
  - *Watched folders*: a new temp folder watched through Settings; the extra ride dropped
    into it imported once it settles, listed with its link, announced on the page, opened from
    the notice, and the notice dismissed; stopping watching keeps the ride. Scan now finding a
    broken file (listed) and a ride already in the library (not listed, not announced); on a
    phone, long paths wrap. Paths that aren't full, don't exist, or are outside the temp
    folder refused with the reason. Accessibility scans with the notice and the latest files.
  - *Similar rides*: the other rides on the loop listed as the same route, newest first, and
    opened; the effort tab reached with the arrow keys, closest first, no HR-only rides; the
    indoor ride (no GPS) and the Zwift ride (alone in Watopia) saying why there's nothing;
    progress on the loop, oldest first with this ride marked, by speed then power, opening
    the oldest ride, the ride without power's TSS marked "HR*" and explained, and no progress
    section for a ride alone on its route.
  - *Ride stats*: switching the charts between time and distance; the zoom bar's label, and
    Show whole ride enabled once zoomed in and resetting it.
  - *Security*: the app served with its Content-Security-Policy, and the library, a ride
    with its charts, Trends, Bikes and Settings working under it with no violations; a
    remembered theme applied by the theme script alone, before the app's code runs. A page
    on another site (served by the test on another local port, since Chromium already
    keeps public sites away from localhost) uploading to the import: fitlib answers 403,
    read from the browser's network log, and the page can't see the answer.
  - *Phone width*: the library, ride, compare and trends pages (and Settings, in *Watched
    folders*) don't scroll sideways on a 390 px
    screen, and pass the accessibility scan there (wide tables scroll in boxes a keyboard
    can reach).
  - *Compare*: two rides picked in the library and compared (figures side by side, lined
    up by distance with a time gap, zoomed in and back out), picks kept back in the library; a fifth ride selected but not
    compared, picks kept while filtering, cleared; lining up by time, smoothing off and removing rides down to one;
    comparing from Similar rides, with one ride and with the 3 closest.
  - *Accessibility*: axe WCAG 2.2 AA scans of every page (including Bikes, Settings, the
    ride's edit form, both Similar rides tabs, route progress with its table, the compare page
    by distance, by time and with too few rides, and Trends with every table shown and with a
    backwards range) in light mode, dark mode from the system, and dark mode chosen in the
    app.

### Performance check

Not part of CI. Generates synthetic rides over six years, imports them into a temporary
library and times some searches, similar rides and every trend over the six years (each
under 0.2 s for 2,000 rides), whole API requests for a library page of 50 rides and a ride
page (about 20 ms and 15 ms), then an encrypted sync to a local folder (setup, first push,
an unchanged push and a restore):

```bash
uv run python scripts/perf_import.py --rides 2000
```

## License

[MIT](LICENSE)
