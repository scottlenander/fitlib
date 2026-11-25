"""The in-memory catalog's state and the helpers several roles share."""

from __future__ import annotations

from datetime import date

from fitlib.models import (
    AthleteEntry,
    Bike,
    BikeDefault,
    BikeSlot,
    DeletedFile,
    Ride,
    Route,
    WatchedFile,
    WatchFolder,
)
from fitlib.store.interfaces import (
    BikeNotFound,
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


class _Base:
    """The state every role's part shares: rides, bikes, athlete, settings and watch dicts."""

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

    def _require_bike(self, bike_id: str) -> None:
        """Check a bike exists, for rides that name it.

        Args:
            bike_id: The bike's id.

        Raises:
            BikeNotFound: No bike has this id.
        """
        if bike_id not in self._bikes:
            raise BikeNotFound(bike_id)

    def close(self) -> None:
        """Release the catalog's resources."""
        pass
