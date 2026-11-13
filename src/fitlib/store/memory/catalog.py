"""In-memory catalog for tests. Behaves exactly like the SQLite catalog."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from fitlib.models import (
    AthleteEntry,
    Bike,
    BikeDefault,
    BikeSlot,
    BikeTotals,
    Filters,
    Page,
    Ride,
    RideMeta,
    RideSummary,
    SortKey,
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
    ]
    return all(checks)


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
        self._rides[ride_id] = replace(ride, meta=replace(meta, tags=tuple(sorted(meta.tags))))

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

    def replace_summary(self, ride_id: str, summary: RideSummary, metrics_version: int) -> None:
        """Replace a ride's computed figures, keeping its id, import details and metadata.

        Args:
            ride_id: The ride's id.
            summary: The newly computed summary.
            metrics_version: The calculations version that produced it.

        Raises:
            RideNotFound: No ride has this id.
        """
        ride = self.get_ride(ride_id)
        self._rides[ride_id] = replace(ride, summary=summary, metrics_version=metrics_version)

    def ride_ids(self, below_version: int | None = None) -> list[str]:
        """List ride ids, oldest ride first.

        Args:
            below_version: Only rides computed with an older ``metrics_version`` than this.

        Returns:
            The ids.
        """
        rides = sorted(self._rides.values(), key=lambda r: (r.summary.start, r.id))
        return [r.id for r in rides if below_version is None or r.metrics_version < below_version]

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
        values = [
            value
            for ride in self.rides_starting_between(start, end)
            for d, value in (ride.summary.power_curve if kind == "power" else ride.summary.hr_curve)
            if d == duration_s
        ]
        return max(values, default=None)

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

    def add_ride(self, ride: Ride) -> None:
        """Store a new ride, all or nothing.

        Args:
            ride: The ride to add.

        Raises:
            DuplicateRide: A ride with the same sha256 is already stored.
            BikeNotFound: The ride's ``meta.bike_id`` isn't a bike.
        """
        if self.find_by_hash(ride.sha256) is not None:
            raise DuplicateRide(ride.sha256)
        if ride.meta.bike_id is not None:
            self.get_bike(ride.meta.bike_id)
        self._rides[ride.id] = replace(
            ride, meta=replace(ride.meta, tags=tuple(sorted(ride.meta.tags)))
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

    def count(self) -> int:
        """Count the rides in the catalog.

        Returns:
            The number of rides.
        """
        return len(self._rides)

    def close(self) -> None:
        """Release the catalog's resources."""
        pass
