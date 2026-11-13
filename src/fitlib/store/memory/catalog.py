from __future__ import annotations

from datetime import datetime

from fitlib.models import Filters, Page, Ride, SortKey
from fitlib.store.interfaces import (
    MIN_ID_PREFIX,
    AmbiguousRideId,
    DuplicateRide,
    RideNotFound,
    searchable_text,
    words,
)


def _matches_text(ride: Ride, text: str) -> bool:
    ride_words = [w for field in searchable_text(ride).values() for w in words(field)]
    return all(any(w.startswith(q) for w in ride_words) for q in words(text))


def _matches(ride: Ride, f: Filters) -> bool:
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
    def __init__(self) -> None:
        self._rides: dict[str, Ride] = {}

    def add_ride(self, ride: Ride) -> None:
        if self.find_by_hash(ride.sha256) is not None:
            raise DuplicateRide(ride.sha256)
        self._rides[ride.id] = ride

    def get_ride(self, ride_id: str) -> Ride:
        try:
            return self._rides[ride_id]
        except KeyError:
            raise RideNotFound(ride_id) from None

    def resolve_id(self, ref: str) -> str:
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
        return next((r.id for r in self._rides.values() if r.sha256 == sha256), None)

    def rides_starting_between(self, start: datetime, end: datetime) -> list[Ride]:
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
        found = [r for r in self._rides.values() if _matches(r, filters)]
        # Tie-break on start then id; rides with no value for the sort key always go last.
        found.sort(key=lambda r: (r.summary.start, r.id), reverse=descending)
        with_value = [r for r in found if _sort_value(r, sort) is not None]
        without = [r for r in found if _sort_value(r, sort) is None]
        with_value.sort(key=lambda r: _sort_value(r, sort), reverse=descending)
        ordered = with_value + without
        return Page(tuple(ordered[offset : offset + limit]), len(ordered), offset, limit)

    def count(self) -> int:
        return len(self._rides)

    def close(self) -> None:
        pass
