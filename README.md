# Fitlib

A local library for cycling `.fit` files from Zwift and Garmin. It will import rides from a
folder, store them compactly, summarise each ride in readable numbers, find and compare similar
rides, and show trends over time.

The project is built in phases. **Phase 0 (this)** sets up the Python project, synthetic test
fixtures, and CI. There is no app to run yet.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.14 is pinned in `.python-version`; uv
installs it if needed.

```bash
uv sync          # create .venv and install dependencies from uv.lock
```

## Tests

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # formatting (`uv run ruff format .` fixes it)
uv run pytest                  # tests
```

CI runs the same three checks on every pull request (`.github/workflows/ci.yml`).

### Fixtures

All test rides are **synthetic**; no real ride data is committed. They are described in
`tests/fixtures/specs.py` as blocks of constant power, so metrics can be checked against values
worked out by hand. Outdoor rides loop around 50°23′48″N, 3°24′55″E, near Roubaix, France; Zwift
rides loop around Watopia's coordinates.

The `.fit` files in `tests/fixtures/fit/` are generated from the specs and committed. After
changing the specs or the generator, rebuild them:

```bash
uv run python -m tests.fixtures.generate
```

`tests/test_fixtures_current.py` fails if the committed files are out of date.

### What's tested

- **FIT round trip** (`tests/test_fit_roundtrip.py`): rides written with `fit-tool` decode with
  `fitdecode` on Python 3.14 with identical timestamps, power, heart rate, cadence, positions,
  distance, speed, altitude and session details; a truncated file is rejected. This guards both
  libraries, neither of which declares Python 3.14 support.
- **Fixtures are current** (`tests/test_fixtures_current.py`): generation is deterministic and
  the committed files match the specs.
