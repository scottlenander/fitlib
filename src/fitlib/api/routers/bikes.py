"""Bikes, the dated default-bike timeline, and backfilling defaults onto older rides.

Bikes are never deleted, only retired, so rides keep them.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Response

from fitlib.api.deps import StoresDep
from fitlib.api.schemas import (
    BackfillChange,
    BackfillResult,
    BikeCreate,
    BikeOut,
    BikePatch,
    BikeWithTotals,
    DefaultOut,
    DefaultSet,
    bike_out,
    bike_ref,
)
from fitlib.metadata import KEEP
from fitlib.models import BikeDefault, BikeSlot
from fitlib.services import bikes as bike_service

router = APIRouter(prefix="/bikes", tags=["bikes"])


@router.get("")
def list_bikes(stores: StoresDep, include_retired: bool = True) -> list[BikeWithTotals]:
    """List bikes with how much each has been ridden.

    Args:
        stores: The library's stores.
        include_retired: Whether to include retired bikes.

    Returns:
        The bikes, sorted by name.
    """
    return [
        BikeWithTotals(
            **bike_out(t.bike).model_dump(),
            rides=t.rides,
            distance_m=t.distance_m,
            moving_s=t.moving_s,
        )
        for t in stores.catalog.bike_totals()
        if include_retired or not t.bike.retired
    ]


@router.post("", status_code=201)
def add_bike(stores: StoresDep, new: BikeCreate) -> BikeOut:
    """Add a bike.

    Args:
        stores: The library's stores.
        new: The bike's name and kind.

    Returns:
        The new bike, with its id.

    Raises:
        DuplicateBike: Another bike has the name, ignoring case (a 409).
    """
    return bike_out(bike_service.add_bike(stores.catalog, new.name, new.kind))


# Declared before ``/{bike_id}`` so "defaults" and "backfill" are never taken for bike ids.


@router.get("/defaults")
def list_defaults(stores: StoresDep) -> list[DefaultOut]:
    """Show the default-bike timeline.

    Args:
        stores: The library's stores.

    Returns:
        Every entry, by slot and then date.
    """
    return [
        DefaultOut(slot=d.entry.slot, effective_from=d.entry.effective_from, bike=bike_ref(d.bike))
        for d in bike_service.default_timeline(stores.catalog)
    ]


@router.put("/defaults/{slot}/{effective_from}")
def set_default(
    stores: StoresDep, slot: BikeSlot, effective_from: date, body: DefaultSet
) -> DefaultOut:
    """Set the default bike for one kind of ride from a date, replacing any entry then.

    Args:
        stores: The library's stores.
        slot: Which kind of ride.
        effective_from: The first day it applies.
        body: The bike, or ``null`` to stop defaulting from that day.

    Returns:
        The saved entry.

    Raises:
        BikeNotFound: ``bike_id`` isn't a bike (a 404).
    """
    saved = bike_service.set_default(
        stores.catalog, BikeDefault(slot, effective_from, body.bike_id)
    )
    return DefaultOut(slot=slot, effective_from=effective_from, bike=bike_ref(saved.bike))


@router.delete("/defaults/{slot}/{effective_from}", status_code=204)
def delete_default(stores: StoresDep, slot: BikeSlot, effective_from: date) -> Response:
    """Remove a default-bike entry.

    Args:
        stores: The library's stores.
        slot: The entry's kind of ride.
        effective_from: The entry's date.

    Returns:
        An empty response.

    Raises:
        DefaultNotFound: There is no such entry (a 404).
    """
    bike_service.remove_default(stores.catalog, slot, effective_from)
    return Response(status_code=204)


@router.post("/backfill")
def backfill(stores: StoresDep, dry_run: bool = False) -> BackfillResult:
    """Give rides the default bike for their date, as new imports get.

    Rides whose bike was set by hand are never changed.

    Args:
        stores: The library's stores.
        dry_run: Report what would change without saving it.

    Returns:
        How many rides each bike gains.
    """
    changed = bike_service.backfill(stores.catalog, dry_run=dry_run)
    return BackfillResult(
        dry_run=dry_run,
        changes=[BackfillChange(bike=bike_ref(bike), rides=count) for bike, count in changed],
    )


@router.patch("/{bike_id}")
def update_bike(stores: StoresDep, bike_id: str, patch: BikePatch) -> BikeOut:
    """Rename a bike, change its kind, or retire or bring it back.

    Args:
        stores: The library's stores.
        bike_id: The bike's id.
        patch: The changes; fields left out stay as they are.

    Returns:
        The updated bike.

    Raises:
        BikeNotFound: No bike has this id (a 404).
        DuplicateBike: Another bike has the new name (a 409).
    """
    sent = patch.model_fields_set
    updated = bike_service.change_bike(
        stores.catalog,
        stores.catalog.get_bike(bike_id),
        name=patch.name,
        kind=patch.kind if "kind" in sent else KEEP,
        retired=patch.retired,
    )
    return bike_out(updated)
