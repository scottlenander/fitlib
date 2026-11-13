"""Time a large import and some library queries on synthetic rides. Not run in CI.

    uv run python scripts/perf_import.py --rides 2000

Generates rides spread over 2020-2025 (30 min to 2 h, Zwift and Garmin), imports them into a
fresh temporary library, then times a few typical searches. Everything is deleted afterwards
unless ``--keep`` is given.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

# Make the repo root importable (for tests.fixtures), also in spawned worker processes.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitlib.config import Config  # noqa: E402
from fitlib.importer import Importer  # noqa: E402
from fitlib.models import Filters, SortKey  # noqa: E402
from fitlib.store.factory import open_stores  # noqa: E402
from tests.fixtures.generate import build  # noqa: E402
from tests.fixtures.specs import RIDES, Segment  # noqa: E402

FIRST_DAY = datetime(2020, 1, 1, 7, 0, tzinfo=UTC)
TEMPLATES = [s for s in RIDES if s.sport == "cycling" and not s.zip_name]


def make_ride(index: int, total: int) -> tuple[str, bytes]:
    """Ride ``index`` of ``total``, spread evenly over six years so none overlap."""
    template = TEMPLATES[index % len(TEMPLATES)]
    minutes = 30 + (index * 37) % 91  # 30-120 min
    spec = replace(
        template,
        name=f"perf_{index:05d}",
        start=FIRST_DAY + timedelta(days=index * 2190 / total),
        segments=(Segment(seconds=minutes * 60, power=150 + index % 120),),
        pauses=(),
        serial_number=0x0F18_0000 + index,
    )
    return f"{spec.name}.fit", build(spec)


def timed(label: str, fn):
    started = time.perf_counter()
    result = fn()
    print(f"  {label:<40} {time.perf_counter() - started:8.3f} s")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rides", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=None, help="Import workers (default 4).")
    parser.add_argument("--keep", action="store_true", help="Keep the generated files and library.")
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="fitlib-perf-"))
    source_dir, library = root / "fit", root / "library"
    source_dir.mkdir()
    print(f"Working in {root}")

    started = time.perf_counter()
    with ProcessPoolExecutor() as pool:
        rides = pool.map(partial(make_ride, total=args.rides), range(args.rides), chunksize=8)
        for name, data in rides:
            (source_dir / name).write_bytes(data)
    size_mb = sum(p.stat().st_size for p in source_dir.iterdir()) / 1e6
    print(
        f"Generated {args.rides} rides ({size_mb:.0f} MB) in {time.perf_counter() - started:.0f} s"
    )

    try:
        with open_stores(Config(library=library)) as stores:
            importer = Importer(stores.catalog, stores.blobs, stores.streams, workers=args.workers)
            print("Timings:")
            report = timed("import", lambda: importer.run([source_dir]))
            print(f"  -> imported {len(report.imported)}, failed {len(report.failed)}")
            timed("re-import (all duplicates)", lambda: importer.run([source_dir]))
            c = stores.catalog
            timed("list newest 20", lambda: c.search(limit=20))
            timed(
                "list by power, page 10", lambda: c.search(sort=SortKey.POWER, offset=180, limit=20)
            )
            timed("text search 'zwift'", lambda: c.search(Filters(text="zwift"), limit=20))
            timed(
                "one year, outdoor, > 1 h",
                lambda: c.search(
                    Filters(
                        since=datetime(2023, 1, 1, tzinfo=UTC),
                        until=datetime(2024, 1, 1, tzinfo=UTC),
                        indoor=False,
                        min_duration_s=3600,
                    ),
                    limit=20,
                ),
            )
        library_mb = sum(p.stat().st_size for p in library.rglob("*") if p.is_file()) / 1e6
        print(f"Library size: {library_mb:.0f} MB")
    finally:
        if args.keep:
            print(f"Kept {root}")
        else:
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
