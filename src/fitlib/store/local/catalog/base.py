"""The SQLite catalog's connection, migrations and the helpers several roles share."""

from __future__ import annotations

import os
import sqlite3
import struct
import tempfile
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from fitlib.models import (
    GeoSummary,
    Lap,
    OffsetSource,
    Ride,
    RideMeta,
    RideSummary,
    Source,
)
from fitlib.store.interfaces import (
    BadSnapshot,
    BikeNotFound,
    searchable_text,
)

# Columns of ``rides`` that hold the summary (replaced together by ``replace_summary``).
_SUMMARY_COLUMNS = (
    "start_ts", "utc_offset_s", "source", "device", "sport", "sub_sport", "indoor", "elapsed_s",
    "moving_s", "distance_m", "ascent_m", "avg_speed_mps", "max_speed_mps", "avg_power",
    "max_power", "avg_hr", "max_hr", "avg_cadence", "has_power", "has_hr", "has_gps", "np", "kj",
    "vi", "decoupling_pct", "utc_offset_source",
)  # fmt: skip


# How long a connection waits for another to finish writing.
BUSY_TIMEOUT_S = 5.0


def _migrations() -> list[tuple[int, str]]:
    """Read the bundled SQL migrations.

    Returns:
        ``(version, script)`` pairs, oldest first. The version is the number at the start of
        each file name, e.g. ``0001_initial.sql``.
    """
    folder = resources.files("fitlib.store.local") / "migrations"
    found = []
    for entry in folder.iterdir():
        if entry.name.endswith(".sql"):
            found.append((int(entry.name.split("_", 1)[0]), entry.read_text()))
    return sorted(found)


def latest_schema_version() -> int:
    """The newest catalog schema this version of fitlib knows.

    Returns:
        The number of the last bundled migration.
    """
    return _migrations()[-1][0]


# Tables that hold this computer's paths, left out of snapshots.
LOCAL_TABLES = ("watch_files", "watch_folders")


def restore_snapshot(path: Path, data: bytes) -> None:
    """Write a catalog snapshot as a library's catalog file, checking it first.

    The file appears only once it's complete and checked.

    Args:
        path: The catalog file to create. It must not exist yet.
        data: A snapshot from ``SqliteCatalog.snapshot``.

    Raises:
        FileExistsError: ``path`` already exists.
        BadSnapshot: The data isn't a sound SQLite database, or its schema is newer than
            ``latest_schema_version()``.
    """
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-catalog-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        db = sqlite3.connect(tmp)
        try:
            ok = db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            version = db.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.DatabaseError:
            ok, version = False, 0
        finally:
            db.close()
        if not ok:
            raise BadSnapshot("The catalog snapshot is damaged")
        if version > latest_schema_version():
            raise BadSnapshot(
                f"The catalog is from a newer fitlib (schema {version}); update fitlib first"
            )
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _ts(value: datetime) -> int:
    """Convert a time to whole Unix seconds for storage.

    Args:
        value: A timezone-aware time.

    Returns:
        Seconds since 1970-01-01 UTC.
    """
    return int(value.timestamp())


def _dt(value: int) -> datetime:
    """Convert stored Unix seconds back to a time.

    Args:
        value: Seconds since 1970-01-01 UTC.

    Returns:
        The time in UTC, timezone-aware.
    """
    return datetime.fromtimestamp(value, UTC)


class _Base:
    """The connection every role's part shares, its lock, migrations and common helpers.

    Args:
        path: The database file (created if missing), or ``":memory:"``.
    """

    def __init__(self, path: Path | str) -> None:
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, autocommit=True, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT_S * 1000)}")
        if str(path) != ":memory:":
            self._use_wal()
        self._migrate()

    def _use_wal(self) -> None:
        """Switch the database to WAL mode, if it isn't already.

        Switching needs a lock SQLite doesn't wait for, so when another connection is opening
        a new library at the same moment, it's tried again for up to ``BUSY_TIMEOUT_S``.
        """
        deadline = time.monotonic() + BUSY_TIMEOUT_S
        while self._db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            try:
                self._db.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.01)

    def _migrate(self) -> None:
        """Apply every migration newer than the database's ``user_version``, one per transaction.

        Each takes the write lock first and checks the version again, so two connections
        opening a new library at once (the server's watcher and a request) don't both apply
        it: the second waits, then finds it done.
        """
        current = self._db.execute("PRAGMA user_version").fetchone()[0]
        for version, script in _migrations():
            if version <= current:
                continue
            # One script per transaction, so a failed migration leaves the schema as it was.
            self._db.execute("BEGIN IMMEDIATE")
            try:
                current = self._db.execute("PRAGMA user_version").fetchone()[0]
                if version > current:
                    self._db.executescript(f"{script}\nPRAGMA user_version = {version};")
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    @property
    def schema_version(self) -> int:
        """The migration the database is at.

        Returns:
            The number of the last migration applied.
        """
        return self._db.execute("PRAGMA user_version").fetchone()[0]

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection]:
        """Run a block in one write transaction.

        Yields:
            The connection; everything done with it commits together, or rolls back if the
            block raises.
        """
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def _require_bike(self, db: sqlite3.Connection, bike_id: str) -> None:
        """Make sure a bike exists.

        Args:
            db: The connection.
            bike_id: The bike's id.

        Raises:
            BikeNotFound: No bike has this id.
        """
        if db.execute("SELECT 1 FROM bikes WHERE id = ?", (bike_id,)).fetchone() is None:
            raise BikeNotFound(bike_id)

    def _index(self, db: sqlite3.Connection, ride: Ride) -> None:
        """Update a ride's entry in the full-text index.

        Args:
            db: The connection, inside a transaction.
            ride: The ride, as it should now be found.
        """
        bike = None
        if ride.meta.bike_id is not None:
            row = db.execute("SELECT name FROM bikes WHERE id = ?", (ride.meta.bike_id,)).fetchone()
            bike = row["name"] if row else None
        text = searchable_text(ride, bike)
        db.execute("DELETE FROM rides_fts WHERE ride_id = ?", (ride.id,))
        db.execute(
            "INSERT INTO rides_fts (ride_id, name, notes, tags, source, device, bike) "
            "VALUES (:id, :name, :notes, :tags, :source, :device, :bike)",
            {"id": ride.id, **text},
        )

    def _load(self, row: sqlite3.Row) -> Ride:
        """Build a ride from its ``rides`` row plus its laps, location, metadata and tags.

        Args:
            row: The ride's row from the ``rides`` table.

        Returns:
            The full ride.
        """
        ride_id = row["id"]
        db = self._db
        laps = tuple(
            Lap(
                index=r["lap_index"],
                start_offset_s=r["start_offset_s"],
                elapsed_s=r["elapsed_s"],
                distance_m=r["distance_m"],
                avg_power=r["avg_power"],
                max_power=r["max_power"],
                avg_hr=r["avg_hr"],
                max_hr=r["max_hr"],
            )
            for r in db.execute(
                "SELECT * FROM laps WHERE ride_id = ? ORDER BY lap_index", (ride_id,)
            )
        )
        g = db.execute("SELECT * FROM ride_geo WHERE ride_id = ?", (ride_id,)).fetchone()
        geo = (
            GeoSummary(
                g["start_lat"],
                g["start_lon"],
                g["min_lat"],
                g["min_lon"],
                g["max_lat"],
                g["max_lon"],
            )
            if g
            else None
        )
        m = db.execute("SELECT * FROM ride_meta WHERE ride_id = ?", (ride_id,)).fetchone()
        tags = tuple(
            r["name"]
            for r in db.execute(
                "SELECT t.name FROM ride_tags rt JOIN tags t ON t.id = rt.tag_id "
                "WHERE rt.ride_id = ? ORDER BY t.name",
                (ride_id,),
            )
        )
        curves: dict[str, list[tuple[int, float]]] = {"power": [], "hr": []}
        for r in db.execute(
            "SELECT kind, duration_s, value FROM ride_curves WHERE ride_id = ? "
            "ORDER BY kind, duration_s",
            (ride_id,),
        ):
            curves[r["kind"]].append((r["duration_s"], r["value"]))
        bins: dict[str, list[tuple[int, int]]] = {"power": [], "hr": []}
        for r in db.execute(
            "SELECT kind, value, seconds FROM ride_bins WHERE ride_id = ? ORDER BY kind, value",
            (ride_id,),
        ):
            bins[r["kind"]].append((r["value"], r["seconds"]))
        meta = RideMeta(
            name=m["name"] if m else None,
            notes=m["notes"] if m else None,
            rpe=m["rpe"] if m else None,
            bike_id=m["bike_id"] if m else None,
            tags=tags,
            bike_from_default=bool(m["bike_from_default"]) if m else False,
        )
        summary = RideSummary(
            start=_dt(row["start_ts"]),
            utc_offset_s=row["utc_offset_s"],
            utc_offset_source=OffsetSource(row["utc_offset_source"]),
            source=Source(row["source"]),
            device=row["device"],
            sport=row["sport"],
            sub_sport=row["sub_sport"],
            indoor=bool(row["indoor"]),
            elapsed_s=row["elapsed_s"],
            moving_s=row["moving_s"],
            distance_m=row["distance_m"],
            ascent_m=row["ascent_m"],
            avg_speed_mps=row["avg_speed_mps"],
            max_speed_mps=row["max_speed_mps"],
            avg_power=row["avg_power"],
            max_power=row["max_power"],
            avg_hr=row["avg_hr"],
            max_hr=row["max_hr"],
            avg_cadence=row["avg_cadence"],
            has_power=bool(row["has_power"]),
            has_hr=bool(row["has_hr"]),
            has_gps=bool(row["has_gps"]),
            laps=laps,
            geo=geo,
            np=row["np"],
            kj=row["kj"],
            vi=row["vi"],
            decoupling_pct=row["decoupling_pct"],
            power_curve=tuple(curves["power"]),
            hr_curve=tuple(curves["hr"]),
            power_histogram=tuple(bins["power"]),
            hr_histogram=tuple(bins["hr"]),
        )
        return Ride(
            id=ride_id,
            sha256=row["sha256"],
            summary=summary,
            imported_at=_dt(row["imported_at"]),
            metrics_version=row["metrics_version"],
            source_name=row["source_name"],
            meta=meta,
        )

    def snapshot(self, local_settings: frozenset[str]) -> bytes:
        """Copy the whole catalog as one SQLite file, without this computer's own data.

        Leaves out ``LOCAL_TABLES`` (watched folders and files) and the settings named in
        ``local_settings``. Safe while others write: SQLite's backup copies one
        consistent state.

        Args:
            local_settings: Keys of this computer's own settings, left out.

        Returns:
            The database file's bytes, not in WAL mode.
        """
        with tempfile.TemporaryDirectory(prefix="fitlib-snapshot-") as folder:
            path = Path(folder) / "catalog.sqlite3"
            copy = sqlite3.connect(path, autocommit=True)
            try:
                with self._lock:
                    self._db.backup(copy)
                copy.execute("PRAGMA journal_mode = DELETE")
                for table in LOCAL_TABLES:
                    copy.execute(f"DELETE FROM {table}")
                copy.executemany(
                    "DELETE FROM settings WHERE key = ?", [(key,) for key in local_settings]
                )
                copy.execute("VACUUM")
            finally:
                copy.close()
            data = bytearray(path.read_bytes())
        # The header's file change counter (offset 24) and its copy (92) carry over from the
        # library and move with every write, even to settings left out. Pinning both to 1
        # (still a valid header) makes an unchanged catalog give the same bytes, so a push
        # can skip it.
        struct.pack_into(">I", data, 24, 1)
        struct.pack_into(">I", data, 92, 1)
        return bytes(data)

    def close(self) -> None:
        """Release the catalog's resources."""
        with self._lock:
            self._db.close()
