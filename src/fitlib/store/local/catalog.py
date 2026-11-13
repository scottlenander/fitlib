"""SQLite catalog: WAL mode, numbered SQL migrations, FTS5 text search."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from importlib import resources
from pathlib import Path

from fitlib.models import (
    AthleteEntry,
    Bike,
    BikeDefault,
    BikeKind,
    BikeSlot,
    BikeTotals,
    Filters,
    GeoSummary,
    Lap,
    Page,
    Ride,
    RideMeta,
    RideSummary,
    SortKey,
    Source,
)
from fitlib.store.interfaces import (
    MIN_ID_PREFIX,
    AmbiguousRideId,
    BikeNotFound,
    DuplicateBike,
    DuplicateRide,
    RideNotFound,
    match_bike,
    searchable_text,
    words,
)

_SORT_COLUMNS = {
    SortKey.START: "r.start_ts",
    SortKey.DURATION: "r.moving_s",
    SortKey.DISTANCE: "r.distance_m",
    SortKey.POWER: "r.avg_power",
}

# Columns of ``rides`` that hold the summary (replaced together by ``replace_summary``).
_SUMMARY_COLUMNS = (
    "start_ts", "utc_offset_s", "source", "device", "sport", "sub_sport", "indoor", "elapsed_s",
    "moving_s", "distance_m", "ascent_m", "avg_speed_mps", "max_speed_mps", "avg_power",
    "max_power", "avg_hr", "max_hr", "avg_cadence", "has_power", "has_hr", "has_gps", "np", "kj",
    "vi", "decoupling_pct",
)  # fmt: skip
_RIDE_COLUMNS = ("id", "sha256", "source_name", "imported_at", "metrics_version", *_SUMMARY_COLUMNS)


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


def _ts(value: datetime) -> int:
    """Convert a time to whole Unix seconds for storage.

    Args:
        value: A timezone-aware time.

    Returns:
        Seconds since 1970-01-01 UTC.
    """
    return int(value.timestamp())


def _summary_values(s: RideSummary) -> dict[str, object]:
    """The ``rides`` columns that hold a summary.

    Args:
        s: The summary.

    Returns:
        Values keyed by column name, ready for SQLite.
    """
    return {
        "start_ts": _ts(s.start),
        "utc_offset_s": s.utc_offset_s,
        "source": s.source.value,
        "device": s.device,
        "sport": s.sport,
        "sub_sport": s.sub_sport,
        "indoor": int(s.indoor),
        "elapsed_s": s.elapsed_s,
        "moving_s": s.moving_s,
        "distance_m": s.distance_m,
        "ascent_m": s.ascent_m,
        "avg_speed_mps": s.avg_speed_mps,
        "max_speed_mps": s.max_speed_mps,
        "avg_power": s.avg_power,
        "max_power": s.max_power,
        "avg_hr": s.avg_hr,
        "max_hr": s.max_hr,
        "avg_cadence": s.avg_cadence,
        "has_power": int(s.has_power),
        "has_hr": int(s.has_hr),
        "has_gps": int(s.has_gps),
        "np": s.np,
        "kj": s.kj,
        "vi": s.vi,
        "decoupling_pct": s.decoupling_pct,
    }


def _dt(value: int) -> datetime:
    """Convert stored Unix seconds back to a time.

    Args:
        value: Seconds since 1970-01-01 UTC.

    Returns:
        The time in UTC, timezone-aware.
    """
    return datetime.fromtimestamp(value, UTC)


class SqliteCatalog:
    """The catalog in a SQLite file: WAL mode, numbered migrations, FTS5 text search.

    Safe to share between threads (calls are serialized with a lock). Opening a catalog
    applies any migrations it hasn't had yet.

    Args:
        path: The database file (created if missing), or ``":memory:"``.
    """

    def __init__(self, path: Path | str) -> None:
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, autocommit=True, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA busy_timeout = 5000")
        if str(path) != ":memory:":
            self._db.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    # -- schema -----------------------------------------------------------------------------

    def _migrate(self) -> None:
        """Apply every migration newer than the database's ``user_version``, one per transaction."""
        current = self._db.execute("PRAGMA user_version").fetchone()[0]
        for version, script in _migrations():
            if version > current:
                # One script per transaction, so a failed migration leaves the schema as it was.
                self._db.executescript(
                    f"BEGIN;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;"
                )

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

    # -- writes -----------------------------------------------------------------------------

    def add_ride(self, ride: Ride) -> None:
        """Store a new ride, all or nothing.

        Args:
            ride: The ride to add.

        Raises:
            DuplicateRide: A ride with the same sha256 is already stored.
            BikeNotFound: The ride's ``meta.bike_id`` isn't a bike.
        """
        values = {
            "id": ride.id,
            "sha256": ride.sha256,
            "source_name": ride.source_name,
            "imported_at": _ts(ride.imported_at),
            "metrics_version": ride.metrics_version,
            **_summary_values(ride.summary),
        }
        placeholders = ", ".join(f":{c}" for c in _RIDE_COLUMNS)
        with self._tx() as db:
            try:
                db.execute(
                    f"INSERT INTO rides ({', '.join(_RIDE_COLUMNS)}) VALUES ({placeholders})",
                    values,
                )
            except sqlite3.IntegrityError as exc:
                if "rides.sha256" in str(exc):
                    raise DuplicateRide(ride.sha256) from exc
                raise
            self._write_details(db, ride.id, ride.summary)
            if ride.meta.bike_id is not None:
                self._require_bike(db, ride.meta.bike_id)
            self._write_meta(db, ride.id, ride.meta)
            self._index(db, ride)

    def replace_summary(self, ride_id: str, summary: RideSummary, metrics_version: int) -> None:
        """Replace a ride's computed figures, keeping its id, import details and metadata.

        Args:
            ride_id: The ride's id.
            summary: The newly computed summary.
            metrics_version: The calculations version that produced it.

        Raises:
            RideNotFound: No ride has this id.
        """
        assignments = ", ".join(f"{c} = :{c}" for c in _SUMMARY_COLUMNS)
        with self._tx() as db:
            updated = db.execute(
                f"UPDATE rides SET {assignments}, metrics_version = :metrics_version "
                "WHERE id = :id",
                {**_summary_values(summary), "metrics_version": metrics_version, "id": ride_id},
            ).rowcount
            if not updated:
                raise RideNotFound(ride_id)
            for table in ("laps", "ride_geo", "ride_curves", "ride_bins"):
                db.execute(f"DELETE FROM {table} WHERE ride_id = ?", (ride_id,))
            self._write_details(db, ride_id, summary)
            row = db.execute("SELECT * FROM rides WHERE id = ?", (ride_id,)).fetchone()
            self._index(db, self._load(row))

    def _write_details(self, db: sqlite3.Connection, ride_id: str, s: RideSummary) -> None:
        """Write a summary's laps, location, best efforts and histograms.

        Args:
            db: The connection, inside a transaction.
            ride_id: The ride's id.
            s: The summary.
        """
        db.executemany(
            "INSERT INTO laps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (ride_id, lap.index, lap.start_offset_s, lap.elapsed_s, lap.distance_m,
                 lap.avg_power, lap.max_power, lap.avg_hr, lap.max_hr)
                for lap in s.laps
            ],
        )  # fmt: skip
        if s.geo is not None:
            g = s.geo
            db.execute(
                "INSERT INTO ride_geo VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ride_id, g.start_lat, g.start_lon, g.min_lat, g.min_lon, g.max_lat, g.max_lon),
            )
        for kind, curve in (("power", s.power_curve), ("hr", s.hr_curve)):
            db.executemany(
                "INSERT INTO ride_curves VALUES (?, ?, ?, ?)",
                [(ride_id, kind, duration, value) for duration, value in curve],
            )
        for kind, hist in (("power", s.power_histogram), ("hr", s.hr_histogram)):
            db.executemany(
                "INSERT INTO ride_bins VALUES (?, ?, ?, ?)",
                [(ride_id, kind, value, seconds) for value, seconds in hist],
            )

    def set_athlete_entry(self, entry: AthleteEntry) -> None:
        """Add an athlete history entry, replacing any entry on the same date.

        Args:
            entry: The entry.
        """
        with self._tx() as db:
            db.execute(
                "INSERT OR REPLACE INTO athlete_history VALUES (?, ?, ?, ?)",
                (entry.effective_from.isoformat(), entry.ftp, entry.weight_kg, entry.max_hr),
            )

    def delete_athlete_entry(self, effective_from: date) -> bool:
        """Remove the athlete history entry on a date.

        Args:
            effective_from: The entry's date.

        Returns:
            ``True`` if there was an entry to remove.
        """
        with self._tx() as db:
            deleted = db.execute(
                "DELETE FROM athlete_history WHERE effective_from = ?",
                (effective_from.isoformat(),),
            ).rowcount
        return deleted > 0

    def update_meta(self, ride_id: str, meta: RideMeta) -> None:
        """Replace what the user added to a ride, and refresh its search entry.

        Args:
            ride_id: The ride's id.
            meta: The new name, notes, RPE, bike and tags (tags already normalized).

        Raises:
            RideNotFound: No ride has this id.
            BikeNotFound: ``meta.bike_id`` isn't a bike.
        """
        with self._tx() as db:
            row = db.execute("SELECT * FROM rides WHERE id = ?", (ride_id,)).fetchone()
            if row is None:
                raise RideNotFound(ride_id)
            if meta.bike_id is not None:
                self._require_bike(db, meta.bike_id)
            self._write_meta(db, ride_id, meta)
            self._index(db, self._load(row))

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

    def _check_name_free(self, db: sqlite3.Connection, bike: Bike) -> None:
        """Make sure no other bike has this bike's name, ignoring case.

        Compared in Python with ``casefold`` (not SQLite's ASCII-only NOCASE), so every
        catalog treats names the same way.

        Args:
            db: The connection.
            bike: The bike being added or changed.

        Raises:
            DuplicateBike: Another bike has the same name.
        """
        for row in db.execute("SELECT id, name FROM bikes WHERE id != ?", (bike.id,)):
            if row["name"].casefold() == bike.name.casefold():
                raise DuplicateBike(bike.name)

    def add_bike(self, bike: Bike) -> None:
        """Add a bike.

        Args:
            bike: The bike. Its id must be new.

        Raises:
            DuplicateBike: Another bike has the same name (ignoring case).
        """
        with self._tx() as db:
            self._check_name_free(db, bike)
            db.execute(
                "INSERT INTO bikes VALUES (?, ?, ?, ?)",
                (bike.id, bike.name, bike.kind.value if bike.kind else None, int(bike.retired)),
            )

    def update_bike(self, bike: Bike) -> None:
        """Change a bike's name, kind or retired flag; renaming refreshes its rides' search.

        Args:
            bike: The bike with its new values, matched by id.

        Raises:
            BikeNotFound: No bike has this id.
            DuplicateBike: Another bike has the new name (ignoring case).
        """
        with self._tx() as db:
            self._require_bike(db, bike.id)
            self._check_name_free(db, bike)
            db.execute(
                "UPDATE bikes SET name = ?, kind = ?, retired = ? WHERE id = ?",
                (bike.name, bike.kind.value if bike.kind else None, int(bike.retired), bike.id),
            )
            rows = db.execute(
                "SELECT r.* FROM rides r JOIN ride_meta m ON m.ride_id = r.id WHERE m.bike_id = ?",
                (bike.id,),
            ).fetchall()
            for row in rows:
                self._index(db, self._load(row))

    def set_bike_default(self, entry: BikeDefault) -> None:
        """Add a default-bike entry, replacing any for the same slot and date.

        Args:
            entry: The entry.

        Raises:
            BikeNotFound: ``entry.bike_id`` isn't a bike.
        """
        with self._tx() as db:
            if entry.bike_id is not None:
                self._require_bike(db, entry.bike_id)
            db.execute(
                "INSERT OR REPLACE INTO bike_defaults VALUES (?, ?, ?)",
                (entry.slot.value, entry.effective_from.isoformat(), entry.bike_id),
            )

    def delete_bike_default(self, slot: BikeSlot, effective_from: date) -> bool:
        """Remove the default-bike entry for a slot and date.

        Args:
            slot: The entry's slot.
            effective_from: The entry's date.

        Returns:
            ``True`` if there was an entry to remove.
        """
        with self._tx() as db:
            deleted = db.execute(
                "DELETE FROM bike_defaults WHERE slot = ? AND effective_from = ?",
                (slot.value, effective_from.isoformat()),
            ).rowcount
        return deleted > 0

    def _write_meta(self, db: sqlite3.Connection, ride_id: str, meta: RideMeta) -> None:
        """Write a ride's user metadata and tags, replacing what was there.

        Args:
            db: The connection, inside a transaction.
            ride_id: The ride's id.
            meta: The metadata to store.
        """
        db.execute(
            "INSERT OR REPLACE INTO ride_meta "
            "(ride_id, name, notes, rpe, bike_id, bike_from_default) VALUES (?, ?, ?, ?, ?, ?)",
            (
                ride_id,
                meta.name,
                meta.notes,
                meta.rpe,
                meta.bike_id,
                int(meta.bike_from_default and meta.bike_id is not None),
            ),  # fmt: skip
        )
        db.execute("DELETE FROM ride_tags WHERE ride_id = ?", (ride_id,))
        for tag in meta.tags:
            db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            db.execute(
                "INSERT OR IGNORE INTO ride_tags SELECT ?, id FROM tags WHERE name = ?",
                (ride_id, tag),
            )

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

    # -- reads ------------------------------------------------------------------------------

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

    def get_ride(self, ride_id: str) -> Ride:
        """Load one ride.

        Args:
            ride_id: The ride's full id.

        Returns:
            The ride, including laps, location and metadata.

        Raises:
            RideNotFound: No ride has this id.
        """
        with self._lock:
            row = self._db.execute("SELECT * FROM rides WHERE id = ?", (ride_id,)).fetchone()
            if row is None:
                raise RideNotFound(ride_id)
            return self._load(row)

    def resolve_id(self, ref: str) -> str:
        """Turn a full id or unique prefix into a ride's full id.

        Args:
            ref: A full id, or a prefix of at least ``MIN_ID_PREFIX`` characters.

        Returns:
            The full id of the one matching ride.

        Raises:
            RideNotFound: Nothing matches, or the prefix is too short.
            AmbiguousRideId: The prefix matches several rides.
        """
        with self._lock:
            if self._db.execute("SELECT 1 FROM rides WHERE id = ?", (ref,)).fetchone():
                return ref
            if len(ref) < MIN_ID_PREFIX:
                raise RideNotFound(ref)
            # Ids are UUIDs (hex and dashes), so the prefix can't contain LIKE wildcards.
            candidates = [
                r["id"]
                for r in self._db.execute(
                    "SELECT id FROM rides WHERE id LIKE ? || '%' ORDER BY id", (ref.lower(),)
                )
            ]
        if not candidates:
            raise RideNotFound(ref)
        if len(candidates) > 1:
            raise AmbiguousRideId(ref, candidates)
        return candidates[0]

    def find_by_hash(self, sha256: str) -> str | None:
        """Find the ride imported from a given file.

        Args:
            sha256: Hex sha256 of the original .fit file.

        Returns:
            That ride's id, or ``None``.
        """
        with self._lock:
            row = self._db.execute("SELECT id FROM rides WHERE sha256 = ?", (sha256,)).fetchone()
        return row["id"] if row else None

    def rides_starting_between(self, start: datetime, end: datetime) -> list[Ride]:
        """Load the rides that start inside a time window.

        Args:
            start: Beginning of the window (inclusive).
            end: End of the window (inclusive).

        Returns:
            The rides, oldest first (ties by id).
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM rides WHERE start_ts BETWEEN ? AND ? ORDER BY start_ts, id",
                (_ts(start), _ts(end)),
            ).fetchall()
            return [self._load(r) for r in rows]

    def search(
        self,
        filters: Filters = Filters(),  # noqa: B008
        sort: SortKey = SortKey.START,
        descending: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> Page[Ride]:
        """Find rides, one page at a time.

        Args:
            filters: What to match.
            sort: What to sort by; rides with no value for it come last.
            descending: Largest (or newest) first when true.
            offset: How many matching rides to skip.
            limit: The most rides to return.

        Returns:
            The page of rides and the total number that match.
        """
        where, params = self._where(filters)
        direction = "DESC" if descending else "ASC"
        order = (
            f"{_SORT_COLUMNS[sort]} {direction} NULLS LAST, "
            f"r.start_ts {direction}, r.id {direction}"
        )
        with self._lock:
            total = self._db.execute(f"SELECT COUNT(*) FROM rides r WHERE {where}", params)
            total = total.fetchone()[0]
            rows = self._db.execute(
                f"SELECT r.* FROM rides r WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            items = tuple(self._load(r) for r in rows)
        return Page(items, total, offset, limit)

    @staticmethod
    def _where(f: Filters) -> tuple[str, list[object]]:
        """Turn filters into a SQL condition on the ``rides`` table (aliased ``r``).

        Args:
            f: The filters.

        Returns:
            The condition and its parameters, in order.
        """
        clauses: list[str] = ["1 = 1"]
        params: list[object] = []
        if f.text is not None and (query := words(f.text)):
            # Each word must start some indexed word (FTS5 prefix query, implicit AND).
            clauses.append("r.id IN (SELECT ride_id FROM rides_fts WHERE rides_fts MATCH ?)")
            params.append(" ".join(f'"{w}"*' for w in query))
        if f.since is not None:
            clauses.append("r.start_ts >= ?")
            params.append(_ts(f.since))
        if f.until is not None:
            clauses.append("r.start_ts < ?")
            params.append(_ts(f.until))
        if f.source is not None:
            clauses.append("r.source = ?")
            params.append(f.source.value)
        if f.indoor is not None:
            clauses.append("r.indoor = ?")
            params.append(int(f.indoor))
        if f.min_duration_s is not None:
            clauses.append("r.moving_s >= ?")
            params.append(f.min_duration_s)
        if f.max_duration_s is not None:
            clauses.append("r.moving_s <= ?")
            params.append(f.max_duration_s)
        if f.has_power is not None:
            clauses.append("r.has_power = ?")
            params.append(int(f.has_power))
        for tag in f.tags:
            clauses.append(
                "r.id IN (SELECT rt.ride_id FROM ride_tags rt JOIN tags t ON t.id = rt.tag_id "
                "WHERE t.name = ?)"
            )
            params.append(tag)
        meta = "(SELECT {} FROM ride_meta m WHERE m.ride_id = r.id)"
        if f.bike_id is not None:
            clauses.append(f"{meta.format('bike_id')} = ?")
            params.append(f.bike_id)
        if f.has_bike is not None:
            clauses.append(f"{meta.format('bike_id')} IS {'NOT ' if f.has_bike else ''}NULL")
        if f.min_rpe is not None:
            clauses.append(f"{meta.format('rpe')} >= ?")
            params.append(f.min_rpe)
        if f.max_rpe is not None:
            clauses.append(f"{meta.format('rpe')} <= ?")
            params.append(f.max_rpe)
        return " AND ".join(clauses), params

    def ride_ids(self, below_version: int | None = None) -> list[str]:
        """List ride ids, oldest ride first.

        Args:
            below_version: Only rides computed with an older ``metrics_version`` than this.

        Returns:
            The ids.
        """
        query, params = "SELECT id FROM rides", []
        if below_version is not None:
            query, params = query + " WHERE metrics_version < ?", [below_version]
        with self._lock:
            rows = self._db.execute(query + " ORDER BY start_ts, id", params).fetchall()
        return [r["id"] for r in rows]

    def best_effort_between(
        self, kind: str, duration_s: int, start: datetime, end: datetime
    ) -> float | None:
        """Find the best effort over one duration among rides in a time window.

        Args:
            kind: ``"power"`` or ``"hr"``.
            duration_s: One of ``CURVE_DURATIONS_S``.
            start: Earliest ride start (inclusive).
            end: Latest ride start (inclusive).

        Returns:
            The highest best average, or ``None`` if no ride in the window has one.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT MAX(c.value) FROM ride_curves c JOIN rides r ON r.id = c.ride_id "
                "WHERE c.kind = ? AND c.duration_s = ? AND r.start_ts BETWEEN ? AND ?",
                (kind, duration_s, _ts(start), _ts(end)),
            ).fetchone()
        return row[0]

    def athlete_history(self) -> list[AthleteEntry]:
        """List the athlete history.

        Returns:
            Every entry, oldest first.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM athlete_history ORDER BY effective_from"
            ).fetchall()
        return [
            AthleteEntry(
                effective_from=date.fromisoformat(r["effective_from"]),
                ftp=r["ftp"],
                weight_kg=r["weight_kg"],
                max_hr=r["max_hr"],
            )
            for r in rows
        ]

    @staticmethod
    def _bike(row: sqlite3.Row) -> Bike:
        """Build a bike from its row.

        Args:
            row: A row of the ``bikes`` table.

        Returns:
            The bike.
        """
        return Bike(
            id=row["id"],
            name=row["name"],
            kind=BikeKind(row["kind"]) if row["kind"] else None,
            retired=bool(row["retired"]),
        )

    def get_bike(self, bike_id: str) -> Bike:
        """Load one bike.

        Args:
            bike_id: The bike's id.

        Returns:
            The bike.

        Raises:
            BikeNotFound: No bike has this id.
        """
        with self._lock:
            row = self._db.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()
        if row is None:
            raise BikeNotFound(bike_id)
        return self._bike(row)

    def list_bikes(self, include_retired: bool = True) -> list[Bike]:
        """List bikes, sorted by name (ignoring case).

        Args:
            include_retired: Include retired bikes.

        Returns:
            The bikes.
        """
        with self._lock:
            rows = self._db.execute("SELECT * FROM bikes").fetchall()
        bikes = [self._bike(r) for r in rows if include_retired or not r["retired"]]
        return sorted(bikes, key=lambda b: b.name.casefold())

    def resolve_bike(self, ref: str) -> Bike:
        """Find a bike by name: an exact match ignoring case, else a unique prefix.

        Args:
            ref: A bike name or the start of one.

        Returns:
            The one matching bike.

        Raises:
            BikeNotFound: No bike matches.
            AmbiguousBike: The prefix matches several bikes.
        """
        return match_bike(self.list_bikes(), ref)

    def bike_totals(self) -> list[BikeTotals]:
        """Add up rides, distance and riding time for every bike, retired included.

        Returns:
            One entry per bike, sorted by name (ignoring case); bikes without rides count 0.
        """
        with self._lock:
            rows = {
                r["bike_id"]: r
                for r in self._db.execute(
                    "SELECT m.bike_id, COUNT(*) AS rides, COALESCE(SUM(r.distance_m), 0) AS dist, "
                    "COALESCE(SUM(r.moving_s), 0) AS moving FROM ride_meta m "
                    "JOIN rides r ON r.id = m.ride_id WHERE m.bike_id IS NOT NULL "
                    "GROUP BY m.bike_id"
                )
            }
        totals = []
        for bike in self.list_bikes():
            row = rows.get(bike.id)
            totals.append(
                BikeTotals(
                    bike=bike,
                    rides=row["rides"] if row else 0,
                    distance_m=float(row["dist"]) if row else 0.0,
                    moving_s=int(row["moving"]) if row else 0,
                )
            )
        return totals

    def tag_counts(self) -> list[tuple[str, int]]:
        """Count how many rides use each tag.

        Returns:
            ``(tag, rides)`` for every tag in use, sorted by tag.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT t.name, COUNT(*) AS n FROM ride_tags rt JOIN tags t ON t.id = rt.tag_id "
                "GROUP BY t.id ORDER BY t.name"
            ).fetchall()
        return [(r["name"], r["n"]) for r in rows]

    def bike_defaults(self) -> list[BikeDefault]:
        """List the dated default-bike entries.

        Returns:
            Every entry, by slot then date.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM bike_defaults ORDER BY slot, effective_from"
            ).fetchall()
        return [
            BikeDefault(
                slot=BikeSlot(r["slot"]),
                effective_from=date.fromisoformat(r["effective_from"]),
                bike_id=r["bike_id"],
            )
            for r in rows
        ]

    def count(self) -> int:
        """Count the rides in the catalog.

        Returns:
            The number of rides.
        """
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM rides").fetchone()[0]

    def close(self) -> None:
        """Release the catalog's resources."""
        with self._lock:
            self._db.close()
