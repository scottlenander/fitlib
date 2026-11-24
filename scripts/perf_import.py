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
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path

# Make the repo root importable (for tests.fixtures), also in spawned worker processes.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitlib.analysis import trends  # noqa: E402
from fitlib.analysis.similar import similar_efforts, similar_routes  # noqa: E402
from fitlib.analysis.training import athlete_profile, training  # noqa: E402
from fitlib.config import Config  # noqa: E402
from fitlib.models import Filters, SortKey  # noqa: E402
from fitlib.services.importing import Importer  # noqa: E402
from fitlib.store.factory import (  # noqa: E402
    latest_schema_version,
    library_blobs,
    open_remote,
    open_stores,
    restore_catalog,
    snapshot_catalog,
)
from fitlib.sync.crypto import Keys  # noqa: E402
from fitlib.sync.engine import LocalLibrary, push, read_keyfile, restore, setup  # noqa: E402
from fitlib.sync.keys import MemoryKeyStore  # noqa: E402
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

            def page_with_training():
                page = c.search(limit=50)
                athlete = athlete_profile(c)
                return [training(c, ride, athlete) for ride in page.items]

            timed("library page of 50 with training figures", page_with_training)
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
            # Worst case for route matching: every synthetic ride laps one of two loops.
            newest = c.search(Filters(indoor=False), limit=1).items[0]
            timed("similar routes (newest outdoor ride)", lambda: similar_routes(c, newest))
            timed("similar efforts (newest outdoor ride)", lambda: similar_efforts(c, newest))
            # Trends over the whole six years: the worst case for each view.
            first, last = date(2020, 1, 1), date(2025, 12, 31)
            week, month = trends.Period.WEEK, trends.Period.MONTH
            timed("trends: volume by week, all", lambda: trends.volume(c, week, first, last))
            timed("trends: fitness, all days", lambda: trends.fitness(c, first, last))
            timed("trends: FTP by week, all", lambda: trends.ftp_history(c, week, first, last))
            timed("trends: FTP by month, all", lambda: trends.ftp_history(c, month, first, last))
            timed("trends: efficiency, all", lambda: trends.efficiency(c, first, last))
            timed("trends: power curve, all", lambda: trends.best_curve(c, "power", first, last))
            timed("trends: route progress (newest)", lambda: trends.route_progress(c, newest))

            # Encrypted sync to a local folder (real Argon2id settings; a memory keychain).
            sync_dir = root / "sync"
            sync_dir.mkdir()
            remote, keystore = open_remote(sync_dir), MemoryKeyStore()
            passphrase = "perf passphrase 123"
            timed("sync: setup (Argon2id)", lambda: setup(c, remote, keystore, passphrase))
            local = LocalLibrary(
                c, stores.blobs, partial(snapshot_catalog, stores), latest_schema_version()
            )
            keys = Keys.from_master(keystore.keys[next(iter(keystore.keys))])
            first_push = timed("sync: first push, all", lambda: push(local, remote, keys))
            print(f"  -> uploaded {first_push.uploaded_bytes / 1e6:.0f} MB")
            timed("sync: push, nothing changed", lambda: push(local, remote, keys))
            restored = Config(library=root / "restored")
            timed(
                "sync: restore, all",
                lambda: restore(
                    remote,
                    read_keyfile(remote, passphrase),
                    library_blobs(restored),
                    partial(restore_catalog, restored),
                    latest_schema_version(),
                ),
            )
            sync_mb = sum(p.stat().st_size for p in sync_dir.rglob("*") if p.is_file()) / 1e6
            print(f"  -> sync folder {sync_mb:.0f} MB")
        library_mb = sum(p.stat().st_size for p in library.rglob("*") if p.is_file()) / 1e6
        print(f"Library size: {library_mb:.0f} MB")
    finally:
        if args.keep:
            print(f"Kept {root}")
        else:
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
