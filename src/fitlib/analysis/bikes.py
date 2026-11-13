"""Applying the dated default bikes to rides already in the library."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from fitlib.metadata import default_bike
from fitlib.models import Filters
from fitlib.store.interfaces import CatalogStore


def backfill_bikes(catalog: CatalogStore, dry_run: bool = False) -> Counter[str]:
    """Give rides without a bike the default bike for their kind and date.

    Rides that already have a bike, including one set by hand, are never changed.

    Args:
        catalog: The library's catalog.
        dry_run: Only count what would change.

    Returns:
        How many rides got (or would get) each bike, by bike id.
    """
    defaults = catalog.bike_defaults()
    if not defaults:
        return Counter()
    without = catalog.search(Filters(has_bike=False), limit=max(1, catalog.count()))
    assigned: Counter[str] = Counter()
    for ride in without.items:
        bike_id = default_bike(defaults, ride.summary)
        if bike_id is None:
            continue
        assigned[bike_id] += 1
        if not dry_run:
            catalog.update_meta(ride.id, replace(ride.meta, bike_id=bike_id))
    return assigned
