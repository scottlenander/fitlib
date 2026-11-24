"""Deleting rides: their catalog entries, streams and original files.

The catalog entries go first, all or none. The blobs follow; if that's interrupted, a
leftover file takes space but nothing points at it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from fitlib.models import Ride
from fitlib.store.interfaces import BlobStore, RideCatalog
from fitlib.store.streams import StreamStore, raw_key

log = logging.getLogger(__name__)


def delete_rides(
    catalog: RideCatalog,
    blobs: BlobStore,
    streams: StreamStore,
    ride_ids: Sequence[str],
    remember: bool = True,
) -> list[Ride]:
    """Delete rides with their streams and original files.

    The user's own copies of the files (in Zwift's or Garmin's folders) are never touched.

    Args:
        catalog: The library's catalog.
        blobs: The library's blobs.
        streams: The library's streams.
        ride_ids: The rides' full ids.
        remember: Remember the files, so importing them again skips them (off only for
            test set-up that wants a ride to be importable again as if new).

    Returns:
        The deleted rides, as they were.

    Raises:
        RideNotFound: An id isn't a ride; nothing is deleted.
    """
    rides = catalog.delete_rides(ride_ids, remember=remember)
    for ride in rides:
        streams.delete(ride.id, ride.summary.start)
        blobs.delete(raw_key(ride.sha256))
    log.info("Deleted %d ride(s)", len(rides))
    return rides
