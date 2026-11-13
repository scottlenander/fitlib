"""Applying the dated default bikes to rides already in the library."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from fitlib.metadata import default_bike
from fitlib.store.interfaces import CatalogStore

NO_BIKE = "none"


def backfill_bikes(catalog: CatalogStore, dry_run: bool = False) -> Counter[str]:
    """Re-apply the dated default bikes to every ride whose bike wasn't chosen by hand.

    Rides with no bike get the default for their kind and date. Rides whose bike came from a
    default are updated if the defaults now say otherwise (for example after adding an older
    dated default), or cleared if no default covers them any more. A bike set by the user is
    never changed.

    Args:
        catalog: The library's catalog.
        dry_run: Only count what would change.

    Returns:
        How many rides got (or would get) each bike, by bike id; rides whose default bike is
        removed are counted under ``NO_BIKE``.
    """
    defaults = catalog.bike_defaults()
    rides = catalog.search(limit=max(1, catalog.count())).items
    changed: Counter[str] = Counter()
    for ride in rides:
        meta = ride.meta
        if meta.bike_id is not None and not meta.bike_from_default:
            continue  # chosen by the user
        wanted = default_bike(defaults, ride.summary)
        if wanted == meta.bike_id:
            continue
        changed[wanted or NO_BIKE] += 1
        if not dry_run:
            catalog.update_meta(
                ride.id, replace(meta, bike_id=wanted, bike_from_default=wanted is not None)
            )
    return changed
