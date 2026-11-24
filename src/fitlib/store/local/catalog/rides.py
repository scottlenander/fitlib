"""Rides: adding, reading, searching, deleting, routes and figures across many."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime

from fitlib.models import (
    CurveBest,
    DeletedFile,
    Filters,
    OffsetSource,
    Page,
    Ride,
    RideMeta,
    RideSummary,
    Route,
    SortKey,
    Source,
    TrendRow,
)
from fitlib.store.interfaces import (
    MIN_ID_PREFIX,
    AmbiguousRideId,
    DuplicateRide,
    RideNotFound,
    words,
)
from fitlib.store.local.catalog.base import (
    _SUMMARY_COLUMNS,
    _Base,
    _dt,
    _ts,
)

_SORT_COLUMNS = {
    SortKey.START: "r.start_ts",
    SortKey.DURATION: "r.moving_s",
    SortKey.DISTANCE: "r.distance_m",
    SortKey.POWER: "r.avg_power",
}


_RIDE_COLUMNS = ("id", "sha256", "source_name", "imported_at", "metrics_version", *_SUMMARY_COLUMNS)


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
        "utc_offset_source": s.utc_offset_source.value,
    }


class _Rides(_Base):
    """Rides: adding, reading, searching, deleting, routes and figures across many."""

    def add_ride(self, ride: Ride, route: Route = frozenset()) -> None:
        """Store a new ride, all or nothing.

        Args:
            ride: The ride to add.
            route: The ride's route fingerprint; empty for rides without positions.

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
            self._write_route(db, ride.id, route)
            if ride.meta.bike_id is not None:
                self._require_bike(db, ride.meta.bike_id)
            self._write_meta(db, ride.id, ride.meta)
            self._index(db, ride)
            # Importing a deleted ride's file on purpose brings it back for good.
            db.execute("DELETE FROM deleted_files WHERE sha256 = ?", (ride.sha256,))

    def delete_rides(self, ride_ids: Sequence[str], remember: bool = True) -> list[Ride]:
        """Remove rides and everything the catalog holds for them, all or none.

        Args:
            ride_ids: The rides' full ids (a repeated id counts once).
            remember: Record each ride's file in ``deleted_files``, so imports skip it.

        Returns:
            The rides as they were.

        Raises:
            RideNotFound: An id isn't a ride; nothing is deleted.
        """
        with self._lock:
            rides = [self.get_ride(i) for i in dict.fromkeys(ride_ids)]
            now = _ts(datetime.now(UTC))
            with self._tx() as db:
                for ride in rides:
                    # Laps, location, route, curves, histograms, metadata and tags go with it
                    # (ON DELETE CASCADE); the search index is maintained by hand.
                    db.execute("DELETE FROM rides_fts WHERE ride_id = ?", (ride.id,))
                    db.execute("DELETE FROM rides WHERE id = ?", (ride.id,))
                    if remember:
                        db.execute(
                            "INSERT INTO deleted_files (sha256, name, deleted_at) "
                            "VALUES (?, ?, ?) ON CONFLICT (sha256) DO UPDATE SET "
                            "name = excluded.name, deleted_at = excluded.deleted_at",
                            (ride.sha256, ride.source_name, now),
                        )
        return rides

    def deleted_file(self, sha256: str) -> DeletedFile | None:
        """Look up a file whose ride was deleted.

        Args:
            sha256: The file's hash.

        Returns:
            When and as what it was deleted, or ``None``.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT sha256, name, deleted_at FROM deleted_files WHERE sha256 = ?", (sha256,)
            ).fetchone()
        if row is None:
            return None
        return DeletedFile(row["sha256"], row["name"], _dt(row["deleted_at"]))

    def replace_summary(
        self,
        ride_id: str,
        summary: RideSummary,
        metrics_version: int,
        route: Route = frozenset(),
    ) -> None:
        """Replace a ride's computed figures, keeping its id, import details and metadata.

        Args:
            ride_id: The ride's id.
            summary: The newly computed summary.
            metrics_version: The calculations version that produced it.
            route: The ride's newly computed route fingerprint (replaces the old one).

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
            for table in ("laps", "ride_geo", "ride_curves", "ride_bins", "ride_route"):
                db.execute(f"DELETE FROM {table} WHERE ride_id = ?", (ride_id,))
            self._write_details(db, ride_id, summary)
            self._write_route(db, ride_id, route)
            row = db.execute("SELECT * FROM rides WHERE id = ?", (ride_id,)).fetchone()
            self._index(db, self._load(row))

    def _write_route(self, db: sqlite3.Connection, ride_id: str, route: Route) -> None:
        """Write a ride's route cells.

        Args:
            db: The connection, inside a transaction.
            ride_id: The ride's id.
            route: Its cells.
        """
        db.executemany(
            "INSERT INTO ride_route (ride_id, cell) VALUES (?, ?)",
            [(ride_id, cell) for cell in sorted(route)],
        )

    def route_cells(self, ride_id: str) -> Route:
        """Load a ride's route fingerprint.

        Args:
            ride_id: The ride's full id.

        Returns:
            The cells it passed through; empty for rides without positions.

        Raises:
            RideNotFound: No ride has this id.
        """
        self._require_ride(ride_id)
        rows = self._db.execute("SELECT cell FROM ride_route WHERE ride_id = ?", (ride_id,))
        return frozenset(cell for (cell,) in rows)

    def route_candidates(self, ride_id: str, limit: int = 50) -> list[tuple[str, int]]:
        """Find the rides that share the most route cells with a ride.

        Args:
            ride_id: The ride's full id.
            limit: The most rides to return.

        Returns:
            ``(other ride's id, cells shared)``, most shared first (ties by id).

        Raises:
            RideNotFound: No ride has this id.
        """
        self._require_ride(ride_id)
        rows = self._db.execute(
            "SELECT other.ride_id, COUNT(*) AS shared FROM ride_route AS mine "
            "JOIN ride_route AS other ON other.cell = mine.cell AND other.ride_id != mine.ride_id "
            "WHERE mine.ride_id = ? GROUP BY other.ride_id ORDER BY shared DESC, other.ride_id "
            "LIMIT ?",
            (ride_id, limit),
        )
        return [(other, shared) for other, shared in rows]

    def _require_ride(self, ride_id: str) -> None:
        """Check that a ride exists.

        Args:
            ride_id: The ride's full id.

        Raises:
            RideNotFound: No ride has this id.
        """
        if self._db.execute("SELECT 1 FROM rides WHERE id = ?", (ride_id,)).fetchone() is None:
            raise RideNotFound(ride_id)

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

    def update_metas(self, metas: Mapping[str, RideMeta]) -> None:
        """Replace what the user added to several rides in one transaction.

        Args:
            metas: Each ride's id and its new metadata (tags already normalized).

        Raises:
            RideNotFound: A ride id isn't a ride; nothing is changed.
            BikeNotFound: A ``bike_id`` isn't a bike; nothing is changed.
        """
        with self._tx() as db:
            for bike_id in {m.bike_id for m in metas.values() if m.bike_id is not None}:
                self._require_bike(db, bike_id)
            for ride_id, meta in metas.items():
                row = db.execute("SELECT * FROM rides WHERE id = ?", (ride_id,)).fetchone()
                if row is None:
                    raise RideNotFound(ride_id)
                self._write_meta(db, ride_id, meta)
                self._index(db, self._load(row))

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
        if (box := f.starts_in) is not None:
            clauses.append(
                "r.id IN (SELECT ride_id FROM ride_geo WHERE start_lat BETWEEN ? AND ? "
                "AND start_lon BETWEEN ? AND ?)"
            )
            params += [box.min_lat, box.max_lat, box.min_lon, box.max_lon]
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

    def trend_rows(self, start: datetime | None, end: datetime | None) -> list[TrendRow]:
        """Read the figures trends need for every ride in a time window, in one go.

        Args:
            start: Earliest ride start (inclusive), or ``None`` for no lower bound.
            end: Latest ride start (inclusive), or ``None`` for no upper bound.

        Returns:
            One row per ride, oldest first (ties by id).
        """
        query = (
            "SELECT r.id, r.start_ts, r.utc_offset_s, r.source, r.indoor, r.moving_s, "
            "r.distance_m, r.ascent_m, r.kj, r.np, r.avg_hr, r.decoupling_pct, "
            "c.value AS best_20min_power, h.hr_squared_s FROM rides r LEFT JOIN ride_curves c "
            "ON c.ride_id = r.id AND c.kind = 'power' AND c.duration_s = 1200 "
            "LEFT JOIN (SELECT ride_id, SUM(seconds * value * value) AS hr_squared_s "
            "FROM ride_bins WHERE kind = 'hr' GROUP BY ride_id) h ON h.ride_id = r.id "
            "WHERE 1 = 1"
        )
        params: list[int] = []
        if start is not None:
            query += " AND r.start_ts >= ?"
            params.append(_ts(start))
        if end is not None:
            query += " AND r.start_ts <= ?"
            params.append(_ts(end))
        with self._lock:
            rows = self._db.execute(query + " ORDER BY r.start_ts, r.id", params).fetchall()
        return [
            TrendRow(
                id=r["id"],
                start=_dt(r["start_ts"]),
                utc_offset_s=r["utc_offset_s"],
                source=Source(r["source"]),
                indoor=bool(r["indoor"]),
                moving_s=r["moving_s"],
                distance_m=r["distance_m"],
                ascent_m=r["ascent_m"],
                kj=r["kj"],
                np=r["np"],
                avg_hr=r["avg_hr"],
                decoupling_pct=r["decoupling_pct"],
                best_20min_power=r["best_20min_power"],
                hr_squared_s=r["hr_squared_s"],
            )
            for r in rows
        ]

    def best_curve_between(self, kind: str, start: datetime, end: datetime) -> list[CurveBest]:
        """Find the best effort at every duration among rides in a time window.

        Args:
            kind: ``"power"`` or ``"hr"``.
            start: Earliest ride start (inclusive).
            end: Latest ride start (inclusive).

        Returns:
            One entry per duration any ride in the window has, shortest first. Ties go to the
            earliest ride.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT duration_s, value, ride_id, start_ts FROM ("
                " SELECT c.duration_s, c.value, c.ride_id, r.start_ts, ROW_NUMBER() OVER ("
                "  PARTITION BY c.duration_s ORDER BY c.value DESC, r.start_ts, r.id) AS n"
                " FROM ride_curves c JOIN rides r ON r.id = c.ride_id"
                " WHERE c.kind = ? AND r.start_ts BETWEEN ? AND ?"
                ") WHERE n = 1 ORDER BY duration_s",
                (kind, _ts(start), _ts(end)),
            ).fetchall()
        return [
            CurveBest(r["duration_s"], r["value"], r["ride_id"], _dt(r["start_ts"])) for r in rows
        ]

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

    def rides_by_offset_source(
        self, sources: Iterable[OffsetSource]
    ) -> list[tuple[str, datetime, int | None]]:
        """List rides whose time zone came from one of some sources.

        Args:
            sources: The sources, e.g. the default time zone and none.

        Returns:
            ``(id, start, utc_offset_s)`` for each, oldest first.
        """
        wanted = [s.value for s in sources]
        marks = ", ".join("?" for _ in wanted)
        with self._lock:
            rows = self._db.execute(
                "SELECT id, start_ts, utc_offset_s FROM rides "
                f"WHERE utc_offset_source IN ({marks}) ORDER BY start_ts, id",
                wanted,
            ).fetchall()
        return [(r["id"], _dt(r["start_ts"]), r["utc_offset_s"]) for r in rows]

    def set_utc_offsets(self, offsets: dict[str, tuple[int | None, OffsetSource]]) -> None:
        """Change rides' time zones, keeping everything else.

        Args:
            offsets: For each ride id, its new offset from UTC and where it came from.

        Raises:
            RideNotFound: A ride doesn't exist (nothing is changed).
        """
        with self._tx() as db:
            for ride_id, (offset, source) in offsets.items():
                updated = db.execute(
                    "UPDATE rides SET utc_offset_s = ?, utc_offset_source = ? WHERE id = ?",
                    (offset, source.value, ride_id),
                ).rowcount
                if not updated:
                    raise RideNotFound(ride_id)
                # The default name (and so the search index) has the ride's local date.
                row = db.execute("SELECT * FROM rides WHERE id = ?", (ride_id,)).fetchone()
                self._index(db, self._load(row))

    def count(self) -> int:
        """Count the rides in the catalog.

        Returns:
            The number of rides.
        """
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM rides").fetchone()[0]
