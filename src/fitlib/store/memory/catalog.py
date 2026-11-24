"""In-memory catalog for tests. Behaves exactly like the SQLite catalog."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime

from fitlib.models import (
    AthleteEntry,
    Bike,
    BikeDefault,
    BikeSlot,
    BikeTotals,
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
    TrendRow,
    WatchedFile,
    WatchFolder,
    WatchOutcome,
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


def _matches_text(ride: Ride, bike_name: str | None, text: str) -> bool:
    """Check a ride against a text search, the same way FTS5 prefix queries do.

    Args:
        ride: The ride.
        bike_name: The name of the ride's bike, if any.
        text: The search text.

    Returns:
        ``True`` if every word of ``text`` starts some word of the ride's searchable text.
    """
    fields = searchable_text(ride, bike_name).values()
    ride_words = [w for field in fields for w in words(field)]
    return all(any(w.startswith(q) for w in ride_words) for q in words(text))


def _matches(ride: Ride, bike_name: str | None, f: Filters) -> bool:
    """Check a ride against every filter.

    Args:
        ride: The ride.
        bike_name: The name of the ride's bike, if any.
        f: The filters; ``None`` fields match everything.

    Returns:
        ``True`` if the ride passes them all.
    """
    s, m = ride.summary, ride.meta
    checks = [
        f.text is None or _matches_text(ride, bike_name, f.text),
        all(tag in m.tags for tag in f.tags),
        f.bike_id is None or m.bike_id == f.bike_id,
        f.has_bike is None or (m.bike_id is not None) == f.has_bike,
        f.min_rpe is None or (m.rpe is not None and m.rpe >= f.min_rpe),
        f.max_rpe is None or (m.rpe is not None and m.rpe <= f.max_rpe),
        f.since is None or s.start >= f.since,
        f.until is None or s.start < f.until,
        f.source is None or s.source is f.source,
        f.indoor is None or s.indoor == f.indoor,
        f.min_duration_s is None or s.moving_s >= f.min_duration_s,
        f.max_duration_s is None or s.moving_s <= f.max_duration_s,
        f.has_power is None or s.has_power == f.has_power,
        f.starts_in is None
        or (s.geo is not None and f.starts_in.contains(s.geo.start_lat, s.geo.start_lon)),
    ]
    return all(checks)


def _stored(meta: RideMeta) -> RideMeta:
    """Put metadata in the form the SQLite catalog stores it, so both read back the same.

    Args:
        meta: The metadata as given.

    Returns:
        The metadata with tags sorted, and ``bike_from_default`` false when there's no bike.
    """
    return replace(
        meta,
        tags=tuple(sorted(meta.tags)),
        bike_from_default=meta.bike_from_default and meta.bike_id is not None,
    )


def _sort_value(ride: Ride, sort: SortKey) -> float | None:
    """The value a ride is sorted by.

    Args:
        ride: The ride.
        sort: The sort key.

    Returns:
        A number to sort on, or ``None`` if the ride has no value for the key.
    """
    s = ride.summary
    match sort:
        case SortKey.START:
            return s.start.timestamp()
        case SortKey.DURATION:
            return s.moving_s
        case SortKey.DISTANCE:
            return s.distance_m
        case SortKey.POWER:
            return s.avg_power


class MemoryCatalog:
    """Rides in a dict, for tests. Passes the same contract tests as ``SqliteCatalog``."""

    def __init__(self) -> None:
        self._rides: dict[str, Ride] = {}
        self._athlete: dict[date, AthleteEntry] = {}
        self._bikes: dict[str, Bike] = {}
        self._bike_defaults: dict[tuple[BikeSlot, date], BikeDefault] = {}
        self._routes: dict[str, Route] = {}
        self._settings: dict[str, str] = {}
        self._watch_folders: dict[str, WatchFolder] = {}
        self._watched: dict[str, WatchedFile] = {}
        self._deleted: dict[str, DeletedFile] = {}

    def _bike_name(self, ride: Ride) -> str | None:
        """The name of a ride's bike.

        Args:
            ride: The ride.

        Returns:
            The bike's name, or ``None`` if the ride has no bike.
        """
        bike = self._bikes.get(ride.meta.bike_id or "")
        return bike.name if bike else None

    def update_meta(self, ride_id: str, meta: RideMeta) -> None:
        """Replace what the user added to a ride.

        Args:
            ride_id: The ride's id.
            meta: The new name, notes, RPE, bike and tags.

        Raises:
            RideNotFound: No ride has this id.
            BikeNotFound: ``meta.bike_id`` isn't a bike.
        """
        ride = self.get_ride(ride_id)
        if meta.bike_id is not None:
            self.get_bike(meta.bike_id)
        self._rides[ride_id] = replace(ride, meta=_stored(meta))

    def update_metas(self, metas: Mapping[str, RideMeta]) -> None:
        """Replace what the user added to several rides, all or none of them.

        Args:
            metas: Each ride's id and its new metadata.

        Raises:
            RideNotFound: A ride id isn't a ride; nothing is changed.
            BikeNotFound: A ``bike_id`` isn't a bike; nothing is changed.
        """
        rides = {ride_id: self.get_ride(ride_id) for ride_id in metas}
        for meta in metas.values():
            if meta.bike_id is not None:
                self.get_bike(meta.bike_id)
        for ride_id, meta in metas.items():
            self._rides[ride_id] = replace(rides[ride_id], meta=_stored(meta))

    def _check_name_free(self, bike: Bike) -> None:
        """Make sure no other bike has this bike's name.

        Args:
            bike: The bike being added or changed.

        Raises:
            DuplicateBike: Another bike has the same name (ignoring case).
        """
        for other in self._bikes.values():
            if other.id != bike.id and other.name.casefold() == bike.name.casefold():
                raise DuplicateBike(bike.name)

    def add_bike(self, bike: Bike) -> None:
        """Add a bike.

        Args:
            bike: The bike.

        Raises:
            DuplicateBike: Another bike has the same name (ignoring case).
        """
        self._check_name_free(bike)
        self._bikes[bike.id] = bike

    def update_bike(self, bike: Bike) -> None:
        """Change a bike's name, kind or retired flag.

        Args:
            bike: The bike with its new values, matched by id.

        Raises:
            BikeNotFound: No bike has this id.
            DuplicateBike: Another bike has the new name (ignoring case).
        """
        self.get_bike(bike.id)
        self._check_name_free(bike)
        self._bikes[bike.id] = bike

    def get_bike(self, bike_id: str) -> Bike:
        """Load one bike.

        Args:
            bike_id: The bike's id.

        Returns:
            The bike.

        Raises:
            BikeNotFound: No bike has this id.
        """
        try:
            return self._bikes[bike_id]
        except KeyError:
            raise BikeNotFound(bike_id) from None

    def list_bikes(self, include_retired: bool = True) -> list[Bike]:
        """List bikes, sorted by name (ignoring case).

        Args:
            include_retired: Include retired bikes.

        Returns:
            The bikes.
        """
        bikes = [b for b in self._bikes.values() if include_retired or not b.retired]
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
        return match_bike(list(self._bikes.values()), ref)

    def bike_totals(self) -> list[BikeTotals]:
        """Add up rides, distance and riding time for every bike.

        Returns:
            One entry per bike, sorted by name (ignoring case).
        """
        totals = []
        for bike in self.list_bikes():
            rides = [r for r in self._rides.values() if r.meta.bike_id == bike.id]
            totals.append(
                BikeTotals(
                    bike=bike,
                    rides=len(rides),
                    distance_m=sum(r.summary.distance_m or 0.0 for r in rides),
                    moving_s=sum(r.summary.moving_s for r in rides),
                )
            )
        return totals

    def tag_counts(self) -> list[tuple[str, int]]:
        """Count how many rides use each tag.

        Returns:
            ``(tag, rides)`` for every tag in use, sorted by tag.
        """
        counts: dict[str, int] = {}
        for ride in self._rides.values():
            for tag in ride.meta.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items())

    def bike_defaults(self) -> list[BikeDefault]:
        """List the dated default-bike entries.

        Returns:
            Every entry, by slot then date.
        """
        return [self._bike_defaults[k] for k in sorted(self._bike_defaults)]

    def set_bike_default(self, entry: BikeDefault) -> None:
        """Add a default-bike entry, replacing any for the same slot and date.

        Args:
            entry: The entry.

        Raises:
            BikeNotFound: ``entry.bike_id`` isn't a bike.
        """
        if entry.bike_id is not None:
            self.get_bike(entry.bike_id)
        self._bike_defaults[(entry.slot, entry.effective_from)] = entry

    def delete_bike_default(self, slot: BikeSlot, effective_from: date) -> bool:
        """Remove the default-bike entry for a slot and date.

        Args:
            slot: The entry's slot.
            effective_from: The entry's date.

        Returns:
            ``True`` if there was an entry to remove.
        """
        return self._bike_defaults.pop((slot, effective_from), None) is not None

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
        ride = self.get_ride(ride_id)
        self._rides[ride_id] = replace(ride, summary=summary, metrics_version=metrics_version)
        self._routes[ride_id] = frozenset(route)

    def route_cells(self, ride_id: str) -> Route:
        """Load a ride's route fingerprint.

        Args:
            ride_id: The ride's full id.

        Returns:
            The cells it passed through; empty for rides without positions.

        Raises:
            RideNotFound: No ride has this id.
        """
        self.get_ride(ride_id)
        return self._routes.get(ride_id, frozenset())

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
        mine = self.route_cells(ride_id)
        shared = [
            (other, len(mine & cells))
            for other, cells in self._routes.items()
            if other != ride_id and mine & cells
        ]
        return sorted(shared, key=lambda pair: (-pair[1], pair[0]))[:limit]

    def ride_ids(self, below_version: int | None = None) -> list[str]:
        """List ride ids, oldest ride first.

        Args:
            below_version: Only rides computed with an older ``metrics_version`` than this.

        Returns:
            The ids.
        """
        rides = sorted(self._rides.values(), key=lambda r: (r.summary.start, r.id))
        return [r.id for r in rides if below_version is None or r.metrics_version < below_version]

    def trend_rows(self, start: datetime | None, end: datetime | None) -> list[TrendRow]:
        """Read the figures trends need for every ride in a time window, in one go.

        Args:
            start: Earliest ride start (inclusive), or ``None`` for no lower bound.
            end: Latest ride start (inclusive), or ``None`` for no upper bound.

        Returns:
            One row per ride, oldest first (ties by id).
        """
        rides = sorted(self._rides.values(), key=lambda r: (r.summary.start, r.id))
        return [
            TrendRow(
                id=ride.id,
                start=s.start,
                utc_offset_s=s.utc_offset_s,
                source=s.source,
                indoor=s.indoor,
                moving_s=s.moving_s,
                distance_m=s.distance_m,
                ascent_m=s.ascent_m,
                kj=s.kj,
                np=s.np,
                avg_hr=s.avg_hr,
                decoupling_pct=s.decoupling_pct,
                best_20min_power=dict(s.power_curve).get(1200),
                hr_squared_s=sum(sec * bpm * bpm for bpm, sec in s.hr_histogram) or None,
            )
            for ride in rides
            if (s := ride.summary)
            and (start is None or s.start >= start)
            and (end is None or s.start <= end)
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
        best: dict[int, CurveBest] = {}
        for ride in self.rides_starting_between(start, end):  # oldest first, so ties keep it
            curve = ride.summary.power_curve if kind == "power" else ride.summary.hr_curve
            for duration, value in curve:
                if duration not in best or value > best[duration].value:
                    best[duration] = CurveBest(duration, value, ride.id, ride.summary.start)
        return [best[d] for d in sorted(best)]

    def athlete_history(self) -> list[AthleteEntry]:
        """List the athlete history.

        Returns:
            Every entry, oldest first.
        """
        return [self._athlete[d] for d in sorted(self._athlete)]

    def set_athlete_entry(self, entry: AthleteEntry) -> None:
        """Add an athlete history entry, replacing any entry on the same date.

        Args:
            entry: The entry.
        """
        self._athlete[entry.effective_from] = entry

    def delete_athlete_entry(self, effective_from: date) -> bool:
        """Remove the athlete history entry on a date.

        Args:
            effective_from: The entry's date.

        Returns:
            ``True`` if there was an entry to remove.
        """
        return self._athlete.pop(effective_from, None) is not None

    def add_ride(self, ride: Ride, route: Route = frozenset()) -> None:
        """Store a new ride, all or nothing.

        Args:
            ride: The ride to add.
            route: The ride's route fingerprint; empty for rides without positions.

        Raises:
            DuplicateRide: A ride with the same sha256 is already stored.
            BikeNotFound: The ride's ``meta.bike_id`` isn't a bike.
        """
        if self.find_by_hash(ride.sha256) is not None:
            raise DuplicateRide(ride.sha256)
        if ride.meta.bike_id is not None:
            self.get_bike(ride.meta.bike_id)
        self._rides[ride.id] = replace(ride, meta=_stored(ride.meta))
        self._routes[ride.id] = frozenset(route)
        self._deleted.pop(ride.sha256, None)

    def delete_rides(self, ride_ids: Sequence[str], remember: bool = True) -> list[Ride]:
        """Remove rides and their metadata, all or none.

        Args:
            ride_ids: The rides' full ids (a repeated id counts once).
            remember: Record each ride's file in ``deleted_file``.

        Returns:
            The rides as they were.

        Raises:
            RideNotFound: An id isn't a ride; nothing is deleted.
        """
        rides = [self.get_ride(i) for i in dict.fromkeys(ride_ids)]
        now = datetime.now(UTC).replace(microsecond=0)
        for ride in rides:
            del self._rides[ride.id]
            self._routes.pop(ride.id, None)
            if remember:
                self._deleted[ride.sha256] = DeletedFile(ride.sha256, ride.source_name, now)
        return rides

    def deleted_file(self, sha256: str) -> DeletedFile | None:
        """Look up a file whose ride was deleted.

        Args:
            sha256: The file's hash.

        Returns:
            When and as what it was deleted, or ``None``.
        """
        return self._deleted.get(sha256)

    def get_ride(self, ride_id: str) -> Ride:
        """Load one ride.

        Args:
            ride_id: The ride's full id.

        Returns:
            The ride, including laps, location and metadata.

        Raises:
            RideNotFound: No ride has this id.
        """
        try:
            return self._rides[ride_id]
        except KeyError:
            raise RideNotFound(ride_id) from None

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
        if ref in self._rides:
            return ref
        if len(ref) < MIN_ID_PREFIX:
            raise RideNotFound(ref)
        candidates = sorted(i for i in self._rides if i.startswith(ref))
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
        return next((r.id for r in self._rides.values() if r.sha256 == sha256), None)

    def rides_starting_between(self, start: datetime, end: datetime) -> list[Ride]:
        """Load the rides that start inside a time window.

        Args:
            start: Beginning of the window (inclusive).
            end: End of the window (inclusive).

        Returns:
            The rides, oldest first (ties by id).
        """
        found = [r for r in self._rides.values() if start <= r.summary.start <= end]
        return sorted(found, key=lambda r: (r.summary.start, r.id))

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
        found = [r for r in self._rides.values() if _matches(r, self._bike_name(r), filters)]
        # Tie-break on start then id; rides with no value for the sort key always go last.
        found.sort(key=lambda r: (r.summary.start, r.id), reverse=descending)
        with_value = [r for r in found if _sort_value(r, sort) is not None]
        without = [r for r in found if _sort_value(r, sort) is None]
        with_value.sort(key=lambda r: _sort_value(r, sort), reverse=descending)
        ordered = with_value + without
        return Page(tuple(ordered[offset : offset + limit]), len(ordered), offset, limit)

    def get_setting(self, key: str) -> str | None:
        """Read a library setting.

        Args:
            key: The setting's name.

        Returns:
            Its value, or ``None`` if it isn't set.
        """
        return self._settings.get(key)

    def set_setting(self, key: str, value: str | None) -> None:
        """Set or clear a library setting.

        Args:
            key: The setting's name.
            value: Its new value; ``None`` clears it.
        """
        if value is None:
            self._settings.pop(key, None)
        else:
            self._settings[key] = value

    def rides_by_offset_source(
        self, sources: Iterable[OffsetSource]
    ) -> list[tuple[str, datetime, int | None]]:
        """List rides whose time zone came from one of some sources.

        Args:
            sources: The sources, e.g. the default time zone and none.

        Returns:
            ``(id, start, utc_offset_s)`` for each, oldest first.
        """
        wanted = set(sources)
        rides = sorted(self._rides.values(), key=lambda r: (r.summary.start, r.id))
        return [
            (r.id, r.summary.start, r.summary.utc_offset_s)
            for r in rides
            if r.summary.utc_offset_source in wanted
        ]

    def set_utc_offsets(self, offsets: dict[str, tuple[int | None, OffsetSource]]) -> None:
        """Change rides' time zones, keeping everything else.

        Args:
            offsets: For each ride id, its new offset from UTC and where it came from.

        Raises:
            RideNotFound: A ride doesn't exist (nothing is changed).
        """
        for ride_id in offsets:
            self.get_ride(ride_id)
        for ride_id, (offset, source) in offsets.items():
            ride = self._rides[ride_id]
            summary = replace(ride.summary, utc_offset_s=offset, utc_offset_source=source)
            self._rides[ride_id] = replace(ride, summary=summary)

    def watch_folders(self) -> list[WatchFolder]:
        """List the watched folders.

        Returns:
            Every watched folder, by path.
        """
        return [self._watch_folders[p] for p in sorted(self._watch_folders)]

    def add_watch_folder(self, folder: WatchFolder) -> bool:
        """Start watching a folder.

        Args:
            folder: The folder, with its absolute path.

        Returns:
            ``False`` if it was already watched (nothing changes).
        """
        if folder.path in self._watch_folders:
            return False
        self._watch_folders[folder.path] = folder
        return True

    def remove_watch_folder(self, path: str) -> bool:
        """Stop watching a folder, forgetting the files found in it.

        Args:
            path: The folder's path, as added.

        Returns:
            ``False`` if it wasn't watched.
        """
        if self._watch_folders.pop(path, None) is None:
            return False
        self._watched = {k: v for k, v in self._watched.items() if v.folder != path}
        return True

    def watched_file(self, path: str) -> WatchedFile | None:
        """Look up a file found in a watched folder.

        Args:
            path: The file's absolute path.

        Returns:
            What was recorded for it, or ``None`` if it has never been imported.
        """
        return self._watched.get(path)

    def record_watched_file(self, file: WatchedFile) -> None:
        """Record what importing a watched file did, replacing anything recorded before.

        Args:
            file: The file, its size and modification time, and the outcome.
        """
        self._watched.pop(file.path, None)  # to the end: recorded last
        self._watched[file.path] = file

    def recent_watched_files(self, limit: int = 20) -> list[WatchedFile]:
        """List the latest files from watched folders that weren't already in the library.

        Args:
            limit: The most files to list.

        Returns:
            Imported, skipped and failed files, newest first (duplicates are left out: the
            first scan of an existing folder finds hundreds).
        """
        # Latest recorded first, then newest first (the sort keeps that order for ties).
        files = [
            f for f in reversed(self._watched.values()) if f.outcome is not WatchOutcome.DUPLICATE
        ]
        files.sort(key=lambda f: f.seen_at, reverse=True)
        return files[:limit]

    def watched_file_counts(self) -> dict[str, int]:
        """Count the files found in each watched folder.

        Returns:
            Files recorded per folder path; folders with none are left out.
        """
        counts: dict[str, int] = {}
        for file in self._watched.values():
            counts[file.folder] = counts.get(file.folder, 0) + 1
        return counts

    def count(self) -> int:
        """Count the rides in the catalog.

        Returns:
            The number of rides.
        """
        return len(self._rides)

    def close(self) -> None:
        """Release the catalog's resources."""
        pass
