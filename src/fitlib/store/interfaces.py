"""Storage interfaces. Everything outside ``fitlib.store`` depends on these, never on a backend.

- ``CatalogStore``: one entry per ride (summary, laps, location, user metadata), searchable.
- ``BlobStore``: opaque bytes by key (original .fit files and per-ride streams).

Methods are added as phases need them.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Protocol

from fitlib.models import Filters, Page, Ride, SortKey

MIN_ID_PREFIX = 4


class StoreError(Exception):
    """Base class for storage errors."""


class RideNotFound(StoreError):
    """No ride has the given id, or no ride matches the given id prefix."""


class AmbiguousRideId(StoreError):
    """An id prefix matches more than one ride.

    Args:
        ref: The prefix that was given.
        candidates: Full ids of every matching ride.

    Attributes:
        candidates: Full ids of every matching ride, sorted.
    """

    def __init__(self, ref: str, candidates: list[str]):
        super().__init__(f"{ref!r} matches {len(candidates)} rides; use more characters")
        self.candidates = candidates


class DuplicateRide(StoreError):
    """A ride with the same file hash is already in the catalog."""


class BlobNotFound(StoreError):
    """No blob is stored under the given key."""


class InvalidBlobKey(StoreError):
    """A blob key isn't a relative, lower-case, slash-separated path."""


class CatalogStore(Protocol):
    """One searchable entry per ride: summary, laps, location and the user's metadata."""

    def add_ride(self, ride: Ride) -> None:
        """Store a new ride, all or nothing.

        Args:
            ride: The ride to add. Its id and sha256 must both be new.

        Raises:
            DuplicateRide: A ride with the same sha256 is already stored.
        """
        ...

    def get_ride(self, ride_id: str) -> Ride:
        """Load one ride.

        Args:
            ride_id: The ride's full id.

        Returns:
            The ride, including laps, location and metadata.

        Raises:
            RideNotFound: No ride has this id.
        """
        ...

    def resolve_id(self, ref: str) -> str:
        """Turn what a user typed into a ride's full id.

        Args:
            ref: A full id, or a prefix of at least ``MIN_ID_PREFIX`` characters.

        Returns:
            The full id of the one matching ride.

        Raises:
            RideNotFound: Nothing matches, or the prefix is too short.
            AmbiguousRideId: The prefix matches several rides.
        """
        ...

    def find_by_hash(self, sha256: str) -> str | None:
        """Find the ride imported from a given file.

        Args:
            sha256: Hex sha256 of the original .fit file.

        Returns:
            That ride's id, or ``None`` if the file hasn't been imported.
        """
        ...

    def rides_starting_between(self, start: datetime, end: datetime) -> list[Ride]:
        """Load the rides that start inside a time window.

        Args:
            start: Beginning of the window (inclusive).
            end: End of the window (inclusive).

        Returns:
            The rides, oldest first (ties by id).
        """
        ...

    def search(
        self,
        filters: Filters = Filters(),  # noqa: B008 - frozen dataclass, safe as a default
        sort: SortKey = SortKey.START,
        descending: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> Page[Ride]:
        """Find rides, one page at a time.

        Args:
            filters: What to match; the default matches every ride.
            sort: What to sort by. Rides with no value for it always come last, in either
                direction; ties are broken by start time, then id.
            descending: Largest (or newest) first when true.
            offset: How many matching rides to skip.
            limit: The most rides to return.

        Returns:
            The page of rides and the total number that match.
        """
        ...

    def count(self) -> int:
        """Count the rides in the catalog.

        Returns:
            The number of rides.
        """
        ...

    def close(self) -> None:
        """Release the catalog's resources. It can't be used afterwards."""
        ...


class BlobStore(Protocol):
    """Opaque bytes by key: original .fit files and per-ride streams.

    Keys are relative, lower-case, slash-separated paths (see ``validate_key``).
    """

    def put(self, key: str, data: bytes) -> None:
        """Store bytes, replacing any blob already under the key, atomically.

        Args:
            key: Where to store them.
            data: The bytes.

        Raises:
            InvalidBlobKey: The key isn't valid.
        """
        ...

    def get(self, key: str) -> bytes:
        """Read a blob.

        Args:
            key: The blob's key.

        Returns:
            The stored bytes.

        Raises:
            BlobNotFound: Nothing is stored under the key.
            InvalidBlobKey: The key isn't valid.
        """
        ...

    def exists(self, key: str) -> bool:
        """Check whether a blob is stored.

        Args:
            key: The blob's key.

        Returns:
            ``True`` if something is stored under the key.

        Raises:
            InvalidBlobKey: The key isn't valid.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove a blob. Deleting a missing blob is not an error.

        Args:
            key: The blob's key.

        Raises:
            InvalidBlobKey: The key isn't valid.
        """
        ...

    def list(self, prefix: str = "") -> list[str]:
        """List stored keys.

        Args:
            prefix: Only keys starting with this; all keys by default.

        Returns:
            The matching keys, sorted.
        """
        ...


_KEY = re.compile(r"[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*")


def validate_key(key: str) -> str:
    """Check that a blob key is safe to use as a relative path.

    Args:
        key: The key to check.

    Returns:
        The key, unchanged.

    Raises:
        InvalidBlobKey: The key is empty, absolute, upper-case, has empty parts, or contains
            ``.`` or ``..`` parts.
    """
    if not _KEY.fullmatch(key) or any(part in {".", ".."} for part in key.split("/")):
        raise InvalidBlobKey(f"Invalid blob key: {key!r}")
    return key


# Text search is shared by every catalog so they agree: a query matches when each of its words
# is the start of some word in the ride's name, notes, tags, source or device.
_WORD = re.compile(r"[^\W_]+")


def words(text: str) -> list[str]:
    """Split text into lower-case words the way the catalogs' search does.

    Args:
        text: Any text.

    Returns:
        The runs of letters and digits, lower-cased. Underscores and punctuation separate
        words.
    """
    return [w.lower() for w in _WORD.findall(text)]


def searchable_text(ride: Ride) -> dict[str, str]:
    """Collect the text a ride can be found by.

    Args:
        ride: The ride.

    Returns:
        Its display name, notes, tags, source label and device, by field name. Missing values
        are empty strings.
    """
    s = ride.summary
    return {
        "name": ride.display_name,
        "notes": ride.meta.notes or "",
        "tags": " ".join(ride.meta.tags),
        "source": s.source.label,
        "device": s.device or "",
    }
