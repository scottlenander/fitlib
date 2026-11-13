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
    pass


class RideNotFound(StoreError):
    pass


class AmbiguousRideId(StoreError):
    def __init__(self, ref: str, candidates: list[str]):
        super().__init__(f"{ref!r} matches {len(candidates)} rides; use more characters")
        self.candidates = candidates


class DuplicateRide(StoreError):
    """A ride with the same file hash is already in the catalog."""


class BlobNotFound(StoreError):
    pass


class InvalidBlobKey(StoreError):
    pass


class CatalogStore(Protocol):
    def add_ride(self, ride: Ride) -> None:
        """Store a new ride. Raises ``DuplicateRide`` if its sha256 is already present."""
        ...

    def get_ride(self, ride_id: str) -> Ride:
        """The ride with this exact id. Raises ``RideNotFound``."""
        ...

    def resolve_id(self, ref: str) -> str:
        """Full id for a full id or unique prefix (at least ``MIN_ID_PREFIX`` characters)."""
        ...

    def find_by_hash(self, sha256: str) -> str | None:
        """Id of the ride imported from a file with this sha256, if any."""
        ...

    def rides_starting_between(self, start: datetime, end: datetime) -> list[Ride]:
        """Rides whose start is in [start, end], oldest first."""
        ...

    def search(
        self,
        filters: Filters = Filters(),  # noqa: B008 - frozen dataclass, safe as a default
        sort: SortKey = SortKey.START,
        descending: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> Page[Ride]:
        """Rides matching ``filters``, sorted, one page at a time. Missing values sort last."""
        ...

    def count(self) -> int: ...

    def close(self) -> None: ...


class BlobStore(Protocol):
    def put(self, key: str, data: bytes) -> None:
        """Store ``data`` under ``key``, replacing any existing blob atomically."""
        ...

    def get(self, key: str) -> bytes:
        """Raises ``BlobNotFound``."""
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Remove the blob if present. Not an error if missing."""
        ...

    def list(self, prefix: str = "") -> list[str]:
        """Keys starting with ``prefix``, sorted."""
        ...


_KEY = re.compile(r"[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*")


def validate_key(key: str) -> str:
    """Keys are relative, lower-case, slash-separated paths with no ``..`` or empty parts."""
    if not _KEY.fullmatch(key) or any(part in {".", ".."} for part in key.split("/")):
        raise InvalidBlobKey(f"Invalid blob key: {key!r}")
    return key


# Text search is shared by every catalog so they agree: a query matches when each of its words
# is the start of some word in the ride's name, notes, tags, source or device.
_WORD = re.compile(r"[^\W_]+")


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def searchable_text(ride: Ride) -> dict[str, str]:
    s = ride.summary
    return {
        "name": ride.display_name,
        "notes": ride.meta.notes or "",
        "tags": " ".join(ride.meta.tags),
        "source": s.source.label,
        "device": s.device or "",
    }
