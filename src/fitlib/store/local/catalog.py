"""SQLite catalog: WAL mode, numbered SQL migrations, FTS5 text search."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from fitlib.models import (
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
    DuplicateRide,
    RideNotFound,
    searchable_text,
    words,
)

_SORT_COLUMNS = {
    SortKey.START: "r.start_ts",
    SortKey.DURATION: "r.moving_s",
    SortKey.DISTANCE: "r.distance_m",
    SortKey.POWER: "r.avg_power",
}

_RIDE_COLUMNS = (
    "id", "sha256", "source_name", "imported_at", "metrics_version", "start_ts", "utc_offset_s",
    "source", "device", "sport", "sub_sport", "indoor", "elapsed_s", "moving_s", "distance_m",
    "ascent_m", "avg_speed_mps", "max_speed_mps", "avg_power", "max_power", "avg_hr", "max_hr",
    "avg_cadence", "has_power", "has_hr", "has_gps",
)  # fmt: skip


def _migrations() -> list[tuple[int, str]]:
    folder = resources.files("fitlib.store.local") / "migrations"
    found = []
    for entry in folder.iterdir():
        if entry.name.endswith(".sql"):
            found.append((int(entry.name.split("_", 1)[0]), entry.read_text()))
    return sorted(found)


def _ts(value: datetime) -> int:
    return int(value.timestamp())


def _dt(value: int) -> datetime:
    return datetime.fromtimestamp(value, UTC)


class SqliteCatalog:
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
        current = self._db.execute("PRAGMA user_version").fetchone()[0]
        for version, script in _migrations():
            if version > current:
                # One script per transaction, so a failed migration leaves the schema as it was.
                self._db.executescript(
                    f"BEGIN;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;"
                )

    @property
    def schema_version(self) -> int:
        return self._db.execute("PRAGMA user_version").fetchone()[0]

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
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
        s = ride.summary
        values = {
            "id": ride.id,
            "sha256": ride.sha256,
            "source_name": ride.source_name,
            "imported_at": _ts(ride.imported_at),
            "metrics_version": ride.metrics_version,
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
            db.executemany(
                "INSERT INTO laps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (ride.id, lap.index, lap.start_offset_s, lap.elapsed_s, lap.distance_m,
                     lap.avg_power, lap.max_power, lap.avg_hr, lap.max_hr)
                    for lap in s.laps
                ],
            )  # fmt: skip
            if s.geo is not None:
                g = s.geo
                db.execute(
                    "INSERT INTO ride_geo VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ride.id, g.start_lat, g.start_lon, g.min_lat, g.min_lon, g.max_lat, g.max_lon),
                )
            self._write_meta(db, ride.id, ride.meta)
            self._index(db, ride)

    def _write_meta(self, db: sqlite3.Connection, ride_id: str, meta: RideMeta) -> None:
        db.execute(
            "INSERT OR REPLACE INTO ride_meta VALUES (?, ?, ?, ?, ?)",
            (ride_id, meta.name, meta.notes, meta.rpe, meta.bike_id),
        )
        db.execute("DELETE FROM ride_tags WHERE ride_id = ?", (ride_id,))
        for tag in meta.tags:
            db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            db.execute(
                "INSERT OR IGNORE INTO ride_tags SELECT ?, id FROM tags WHERE name = ?",
                (ride_id, tag),
            )

    def _index(self, db: sqlite3.Connection, ride: Ride) -> None:
        text = searchable_text(ride)
        db.execute("DELETE FROM rides_fts WHERE ride_id = ?", (ride.id,))
        db.execute(
            "INSERT INTO rides_fts (ride_id, name, notes, tags, source, device, bike) "
            "VALUES (?, ?, ?, ?, ?, ?, '')",
            (ride.id, text["name"], text["notes"], text["tags"], text["source"], text["device"]),
        )

    # -- reads ------------------------------------------------------------------------------

    def _load(self, row: sqlite3.Row) -> Ride:
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
        meta = RideMeta(
            name=m["name"] if m else None,
            notes=m["notes"] if m else None,
            rpe=m["rpe"] if m else None,
            bike_id=m["bike_id"] if m else None,
            tags=tags,
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
        with self._lock:
            row = self._db.execute("SELECT * FROM rides WHERE id = ?", (ride_id,)).fetchone()
            if row is None:
                raise RideNotFound(ride_id)
            return self._load(row)

    def resolve_id(self, ref: str) -> str:
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
        with self._lock:
            row = self._db.execute("SELECT id FROM rides WHERE sha256 = ?", (sha256,)).fetchone()
        return row["id"] if row else None

    def rides_starting_between(self, start: datetime, end: datetime) -> list[Ride]:
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
        return " AND ".join(clauses), params

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM rides").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._db.close()
