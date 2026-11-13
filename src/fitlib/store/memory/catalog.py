"""In-memory catalog for tests. Behaves exactly like the SQLite catalog."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from fitlib.models import AthleteEntry, Filters, Page, Ride, RideSummary, SortKey
from fitlib.store.interfaces import (
    MIN_ID_PREFIX,
    AmbiguousRideId,
    DuplicateRide,
    RideNotFound,
    searchable_text,
    words,
)


def _matches_text(ride: Ride, text: str) -> bool:
    """Check a ride against a text search, the same way FTS5 prefix queries do.

    Args:
        ride: The ride.
        text: The search text.

    Returns:
        ``True`` if every word of ``text`` starts some word of the ride's searchable text.
    """
    ride_words = [w for field in searchable_text(ride).values() for w in words(field)]
    return all(any(w.startswith(q) for w in ride_words) for q in words(text))


def _matches(ride: Ride, f: Filters) -> bool:
    """Check a ride against every filter.

    Args:
        ride: The ride.
        f: The filters; ``None`` fields match everything.

    Returns:
        ``True`` if the ride passes them all.
    """
    s = ride.summary
    checks = [
        f.text is None or _matches_text(ride, f.text),
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
        """
        if self.find_by_hash(ride.sha256) is not None:
            raise DuplicateRide(ride.sha256)
        self._rides[ride.id] = ride

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
        found = [r for r in self._rides.values() if _matches(r, filters)]
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
