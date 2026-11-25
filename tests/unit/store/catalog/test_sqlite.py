"""The SQLite catalog only: persisting, opening a new library twice at once, and upgrades."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, date, datetime
from importlib import resources
from pathlib import Path

from fitlib.models import (
    AthleteEntry,
    OffsetSource,
)
from fitlib.store.local import SqliteCatalog
from tests.unit.factories import make_ride


def test_sqlite_catalog_persists_and_is_migrated(tmp_path: Path):
    """A SQLite catalog keeps its rides after being closed and reopened, at the latest schema.

    Given: a catalog file with one ride, closed and opened again.
    Expect: the ride is still there and the schema version is 7 (the latest migration).
    """
    path = tmp_path / "catalog.sqlite3"
    ride = make_ride(start=datetime(2025, 8, 2, tzinfo=UTC))
    first = SqliteCatalog(path)
    first.add_ride(ride)
    first.close()

    reopened = SqliteCatalog(path)
    loaded = reopened.get_ride(ride.id)
    version = reopened.schema_version
    reopened.close()

    assert loaded == ride, "the ride should survive closing and reopening the catalog"
    assert version == 8


def test_new_library_opened_twice_at_once(tmp_path: Path):
    """Two connections opening a new library at the same moment both get the full schema.

    Given: eight threads opening the same new catalog file together (as the server's watcher
    and a request can).
    Expect: every one opens at the latest schema, with no error.
    """
    path = tmp_path / "catalog.sqlite3"
    start = threading.Barrier(8)
    versions: list[int] = []
    errors: list[BaseException] = []

    def open_it() -> None:
        start.wait()
        try:
            catalog = SqliteCatalog(path)
            versions.append(catalog.schema_version)
            catalog.close()
        except BaseException as exc:  # reported below
            errors.append(exc)

    threads = [threading.Thread(target=open_it) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert versions == [8] * 8


def test_phase_1a_database_is_upgraded(tmp_path: Path):
    """A library created before training metrics is upgraded in place when opened.

    Given: a catalog file built with only the initial migration (as phase 1a left it) holding
    one ride.
    Expect: opening it applies migrations 2 to 6; the ride is still there with no training
    figures, so ``recompute`` can fill them in.
    """
    path = tmp_path / "catalog.sqlite3"
    initial = (
        resources.files("fitlib.store.local") / "migrations" / "0001_initial.sql"
    ).read_text()
    db = sqlite3.connect(path)
    db.executescript(f"{initial}\nPRAGMA user_version = 1;")
    db.execute(
        "INSERT INTO rides (id, sha256, source_name, imported_at, metrics_version, start_ts, "
        "source, sport, indoor, elapsed_s, moving_s, has_power, has_hr, has_gps) "
        "VALUES ('abcd1111-0000-4000-8000-000000000001', 'x', 'a.fit', 0, 1, 0, 'zwift', "
        "'cycling', 1, 60, 60, 1, 1, 0)"
    )
    db.commit()
    db.close()

    catalog = SqliteCatalog(path)
    ride = catalog.get_ride("abcd1111-0000-4000-8000-000000000001")
    version = catalog.schema_version
    catalog.close()

    assert version == 8
    assert ride.metrics_version == 1, "the old ride should be marked for recompute"
    assert ride.summary.np is None and ride.summary.power_curve == ()


def test_athlete_entries_survive_the_threshold_hr_upgrade(tmp_path: Path):
    """Upgrading adds threshold heart rate without touching existing athlete entries.

    Given: a catalog at schema version 6 with an athlete entry (FTP 250, max HR 188).
    Expect: after opening it, the entry is unchanged with no threshold heart rate, and one
        can be saved.
    """
    path = tmp_path / "catalog.sqlite3"
    folder = resources.files("fitlib.store.local") / "migrations"
    scripts = sorted(
        (entry.name, entry.read_text()) for entry in folder.iterdir() if entry.name < "0007"
    )
    db = sqlite3.connect(path)
    for _, script in scripts:
        db.executescript(script)
    db.execute("PRAGMA user_version = 6")
    db.execute("INSERT INTO athlete_history VALUES ('2025-01-01', 250, NULL, 188)")
    db.commit()
    db.close()

    catalog = SqliteCatalog(path)
    before = catalog.athlete_history()
    catalog.set_athlete_entry(AthleteEntry(date(2025, 2, 1), threshold_hr=165))
    after = catalog.athlete_history()
    catalog.close()

    assert before == [AthleteEntry(date(2025, 1, 1), ftp=250, max_hr=188)]
    assert after[1] == AthleteEntry(date(2025, 2, 1), threshold_hr=165)


def test_existing_rides_keep_their_time_zone_as_from_their_file(tmp_path: Path):
    """Upgrading marks where each existing ride's time zone came from.

    Given: a catalog at schema version 4 with one ride that has an offset (only ever from its
        file then) and one without.
    Expect: after opening it, the first is marked as from its file and the second as none,
        and there's no default time zone yet.
    """
    path = tmp_path / "catalog.sqlite3"
    folder = resources.files("fitlib.store.local") / "migrations"
    scripts = sorted(
        (entry.name, entry.read_text()) for entry in folder.iterdir() if entry.name < "0005"
    )
    db = sqlite3.connect(path)
    for _, script in scripts:
        db.executescript(script)
    db.execute("PRAGMA user_version = 4")
    for ride_id, offset in (
        ("abcd1111-0000-4000-8000-000000000001", 7200),
        ("abcd2222-0000-4000-8000-000000000002", None),
    ):
        db.execute(
            "INSERT INTO rides (id, sha256, source_name, imported_at, metrics_version, start_ts, "
            "utc_offset_s, source, sport, indoor, elapsed_s, moving_s, has_power, has_hr, "
            "has_gps) VALUES (?, ?, 'a.fit', 0, 5, 0, ?, 'garmin', 'cycling', 0, 60, 60, 1, 1, 0)",
            (ride_id, ride_id, offset),
        )
    db.commit()
    db.close()

    catalog = SqliteCatalog(path)
    sources = [
        catalog.get_ride(ride_id).summary.utc_offset_source
        for ride_id in (
            "abcd1111-0000-4000-8000-000000000001",
            "abcd2222-0000-4000-8000-000000000002",
        )
    ]
    zone = catalog.get_setting("default_time_zone")
    catalog.close()

    assert sources == [OffsetSource.DEVICE, OffsetSource.NONE]
    assert zone is None
