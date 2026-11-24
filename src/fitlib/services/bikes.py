"""Bikes, the dated default-bike timeline, and backfilling defaults onto older rides.

Bikes are never deleted, only retired, so rides keep them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date

from fitlib.analysis.bikes import NO_BIKE, backfill_bikes
from fitlib.metadata import KEEP, Keep
from fitlib.models import Bike, BikeDefault, BikeKind, BikeSlot
from fitlib.services.errors import DefaultNotFound, EmptyBikeName
from fitlib.store.interfaces import CatalogStore


def clean_name(name: str) -> str:
    """Tidy a bike name: spaces trimmed, and runs of spaces made one.

    Args:
        name: The name as typed.

    Returns:
        The tidied name.

    Raises:
        EmptyBikeName: Nothing is left.
    """
    clean = " ".join(name.split())
    if not clean:
        raise EmptyBikeName
    return clean


def add_bike(catalog: CatalogStore, name: str, kind: BikeKind | None = None) -> Bike:
    """Add a bike.

    Args:
        catalog: The library's catalog.
        name: Its name.
        kind: What sort of bike it is.

    Returns:
        The new bike, with its id.

    Raises:
        EmptyBikeName: The name is only spaces.
        DuplicateBike: Another bike has the name, ignoring case.
    """
    bike = Bike(id=str(uuid.uuid4()), name=clean_name(name), kind=kind)
    catalog.add_bike(bike)
    return bike


def change_bike(
    catalog: CatalogStore,
    bike: Bike,
    name: str | None = None,
    kind: BikeKind | None | Keep = KEEP,
    retired: bool | None = None,
) -> Bike:
    """Rename a bike, change its kind, or retire or bring it back.

    Args:
        catalog: The library's catalog.
        bike: The bike as it is.
        name: A new name, or ``None`` to keep it.
        kind: A new kind (``None`` for none), or ``KEEP``.
        retired: Retired or not, or ``None`` to keep it.

    Returns:
        The bike as it is now.

    Raises:
        EmptyBikeName: The new name is only spaces.
        DuplicateBike: Another bike has the new name.
    """
    updated = replace(
        bike,
        name=clean_name(name) if name is not None else bike.name,
        kind=bike.kind if kind is KEEP else kind,
        retired=retired if retired is not None else bike.retired,
    )
    catalog.update_bike(updated)
    return updated


def current_defaults(catalog: CatalogStore) -> dict[BikeSlot, str | None]:
    """Find each kind of ride's most recent default-bike entry.

    Args:
        catalog: The library's catalog.

    Returns:
        The bike id (or ``None`` for "stop defaulting") of the latest entry per slot that has
        any entries.
    """
    latest: dict[BikeSlot, str | None] = {}
    for entry in catalog.bike_defaults():  # by slot, then date
        latest[entry.slot] = entry.bike_id
    return latest


@dataclass(frozen=True)
class DefaultEntry:
    """One entry of the default-bike timeline.

    Attributes:
        entry: The entry.
        bike: Its bike, or ``None`` when the entry stops defaulting.
    """

    entry: BikeDefault
    bike: Bike | None


def default_timeline(catalog: CatalogStore) -> list[DefaultEntry]:
    """List the default-bike timeline with each entry's bike.

    Args:
        catalog: The library's catalog.

    Returns:
        Every entry, by kind of ride and then date.
    """
    bikes = {b.id: b for b in catalog.list_bikes()}
    return [
        DefaultEntry(entry=d, bike=bikes.get(d.bike_id) if d.bike_id else None)
        for d in catalog.bike_defaults()
    ]


def set_default(catalog: CatalogStore, entry: BikeDefault) -> DefaultEntry:
    """Set the default bike for one kind of ride from a date, replacing any entry then.

    Args:
        catalog: The library's catalog.
        entry: The kind of ride, first day and bike (``None`` to stop defaulting).

    Returns:
        The saved entry, with its bike.

    Raises:
        BikeNotFound: The bike isn't a bike.
    """
    catalog.set_bike_default(entry)
    bike = catalog.get_bike(entry.bike_id) if entry.bike_id else None
    return DefaultEntry(entry=entry, bike=bike)


def remove_default(catalog: CatalogStore, slot: BikeSlot, day: date) -> None:
    """Remove a default-bike entry.

    Args:
        catalog: The library's catalog.
        slot: The entry's kind of ride.
        day: The entry's date.

    Raises:
        DefaultNotFound: There's no such entry.
    """
    if not catalog.delete_bike_default(slot, day):
        raise DefaultNotFound(slot.value, f"{day:%Y-%m-%d}")


def backfill(catalog: CatalogStore, dry_run: bool = False) -> list[tuple[Bike | None, int]]:
    """Give rides the default bike for their date, as new imports get.

    Rides whose bike was set by hand are never changed.

    Args:
        catalog: The library's catalog.
        dry_run: Count what would change without saving it.

    Returns:
        Each bike rides gain with how many, most first; ``None`` for rides whose default
        bike is cleared.
    """
    changed = backfill_bikes(catalog, dry_run=dry_run)
    bikes = {b.id: b for b in catalog.list_bikes()}
    return [(None if key == NO_BIKE else bikes[key], n) for key, n in changed.most_common()]
