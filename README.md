# Fitlib

A local library for cycling `.fit` files from Zwift and Garmin. It imports rides from folders,
stores them compactly, and summarises each ride in readable numbers. Later phases add ride
comparison, similar-ride matching, fitness trends and a browser UI.

The project is built in phases. Phase 1a added the core: importing, storage, basic ride
figures and a command line. **Phase 1b (this)** adds training figures (NP, IF, TSS, zones,
best efforts, decoupling), the athlete's FTP/weight/max HR history, `recompute`, and
imperial/metric units. Editing rides, bikes and tags come in phase 1c.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.14 is pinned in `.python-version`; uv
installs it if needed.

```bash
uv sync          # create .venv and install dependencies from uv.lock
```

## Usage

```bash
uv run fitlib import ~/Documents/Zwift/Activities ~/Downloads/garmin_export.zip
uv run fitlib list                          # newest first
uv run fitlib list --source zwift --since 2025-01-01 --sort power
uv run fitlib list --text "arenberg" --outdoor --min-minutes 60
uv run fitlib show 3f2a9c                   # a ride by id prefix (4+ characters)
uv run fitlib show 3f2a9c --units metric    # override the configured units once
uv run fitlib athlete set --from 2025-01-01 --ftp 250 --weight 165 --max-hr 188
uv run fitlib athlete show                  # history, and today's values
uv run fitlib recompute                     # only needed after fitlib's calculations change
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
- **athlete** records FTP, weight and max HR from a date on. Each value carries forward until
  changed, so `--ftp 260` alone keeps the earlier weight. Weight is entered and shown in your
  display units and stored in kg. `athlete remove DATE` deletes an entry.
- **recompute** rebuilds rides from their archived original files. It's only needed when
  fitlib's calculations change (`import` says so); by default it updates just the rides that
  need it, or give ride ids or `--all`.

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
                                      your notes/tags (searchable); athlete history
  blobs/raw/<sha[:2]>/<sha>.fit       every original file, unchanged
  blobs/streams/<year>/<id>.parquet   each ride's 1-second samples (zstd Parquet)
```

Ride ids are random. Location (start point and area) is kept in its own table, and coordinates
are never written to logs.

## Code layout

| Module | Role |
|---|---|
| `fitlib/models.py` | Domain objects shared by every layer |
| `fitlib/ingest/` | Find files (incl. zips), decode with `fitdecode`, normalize to 1 Hz, summarize |
| `fitlib/metrics/` | Ride figures from a 1 Hz stream (basic, power, HR, curves, zones) and FTP-based formulas (`load.py`) |
| `fitlib/analysis/` | FTP-based figures for a ride, from the athlete history or an estimated FTP |
| `fitlib/store/` | `CatalogStore` / `BlobStore` interfaces; `local/` (SQLite + files) and `memory/` backends; `factory.py` picks one |
| `fitlib/importer.py` | Hash, dedupe, analyse in worker processes, store |
| `fitlib/recompute.py` | Rebuild rides from their raw files when calculations change |
| `fitlib/cli.py` | The `fitlib` command |

Only `store/factory.py` chooses a backend; everything else depends on the interfaces.
`import-linter` enforces this and the layering
(`models ← metrics ← ingest ← importer | recompute | analysis ← cli`).

## Tests

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # formatting (`uv run ruff format .` fixes it)
uv run lint-imports            # module boundaries
uv run pytest                  # tests
```

CI runs the same four checks on every pull request (`.github/workflows/ci.yml`).

Each test has a docstring saying what it checks, with **Given** (inputs) and **Expect**
(outcome); assertions that aren't self-explanatory carry a short failure message.

### Fixtures

All test rides are **synthetic**; no real ride data is committed. They are described in
`tests/fixtures/specs.py` as blocks of constant power, so figures can be checked against values
worked out from the spec. Outdoor rides loop around 50°23′48″N, 3°24′55″E, near Roubaix,
France; Zwift rides loop around Watopia's coordinates.

The fixtures cover: a steady Zwift ride, Garmin intervals with a lap per segment, a 10-minute
pause, smart recording (irregular samples), no power meter, an indoor ride without HR or GPS,
a second recording of the Zwift ride, a run, two rides inside a `.zip`, an exact duplicate and
a truncated file.

The files in `tests/fixtures/fit/` are generated from the specs and committed. After changing
the specs or the generator, rebuild them:

```bash
uv run python -m tests.fixtures.generate
```

`tests/test_fixtures_current.py` fails if the committed files are out of date.

### What's tested

- **FIT round trip** (`tests/test_fit_roundtrip.py`): rides written with `fit-tool` decode with
  `fitdecode` on Python 3.14 with identical timestamps, power, heart rate, cadence, positions,
  distance, speed, altitude, session and laps; missing channels stay missing; a truncated file
  is rejected. This guards both libraries, neither of which declares Python 3.14 support.
- **Fixtures are current** (`tests/test_fixtures_current.py`).
- **Storage contracts** (`tests/store/`): one suite runs against every catalog (SQLite, memory)
  and blob store (filesystem, memory): round trips, duplicate hashes, id prefixes, time
  windows, every search filter, text search, sorting with missing values last, paging,
  replacing summaries, best efforts in a window, athlete history, invalid blob keys, Parquet
  streams; plus upgrading a phase 1a database.
- **Ingest** (`tests/ingest/`): scanning folders, files and zips (skipping hidden files and
  macOS zip junk); decoding device, sport, local time, records and laps; rejecting bad files;
  1 Hz normalization (short gaps filled, pauses kept, duplicate timestamps).
- **Metrics** (`tests/metrics/`): elapsed and moving time, distance, speed, climbing, power,
  heart rate, cadence, location box and laps; NP (against a step-by-step reference), kJ, VI,
  best efforts (incl. never across a pause), decoupling, histograms, zone boundaries, IF/TSS,
  estimated FTP and athlete values carrying forward. Expected values are worked out from the
  specs (e.g. 200 W for an hour at FTP 250 → IF 0.80, TSS 64).
- **Training** (`tests/analysis/`): FTP, weight and max HR from the history; estimated FTP
  from the best ride in the window; FTP changes applying without a recompute.
- **Recompute** (`tests/test_recompute.py`): outdated rides brought up to date with metadata
  kept; streams rewritten; missing raw files reported.
- **Importer** (`tests/test_importer.py`): the whole fixture folder (imports, duplicates,
  skips, failures), re-import, stored files and streams, overlapping recordings, the process
  pool, cleanup after a failed write, and no coordinates in logs.
- **CLI** (`tests/test_cli.py`), **config** and **display formatting** (both unit systems).

### Performance check

Not part of CI. Generates synthetic rides over six years, imports them into a temporary
library and times some searches:

```bash
uv run python scripts/perf_import.py --rides 2000
```
