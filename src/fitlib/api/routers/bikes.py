"""Bikes, the dated default-bike timeline, and backfilling defaults onto older rides.

Bikes are never deleted, only retired, so rides keep them.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date

from fastapi import APIRouter, HTTPException, Response

from fitlib.analysis.bikes import NO_BIKE, backfill_bikes
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
from fitlib.models import Bike, BikeDefault, BikeSlot

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
    bike = Bike(id=str(uuid.uuid4()), name=new.name, kind=new.kind)
    stores.catalog.add_bike(bike)
    return bike_out(bike)


# Declared before ``/{bike_id}`` so "defaults" and "backfill" are never taken for bike ids.


@router.get("/defaults")
def list_defaults(stores: StoresDep) -> list[DefaultOut]:
    """Show the default-bike timeline.

    Args:
        stores: The library's stores.

    Returns:
        Every entry, by slot and then date.
    """
    bikes = {b.id: b for b in stores.catalog.list_bikes()}
    return [
        DefaultOut(slot=d.slot, effective_from=d.effective_from, bike=bike_ref(d.bike_id, bikes))
        for d in stores.catalog.bike_defaults()
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
    stores.catalog.set_bike_default(BikeDefault(slot, effective_from, body.bike_id))
    bikes = {b.id: b for b in stores.catalog.list_bikes()}
    return DefaultOut(slot=slot, effective_from=effective_from, bike=bike_ref(body.bike_id, bikes))


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
        HTTPException: 404 if there is no such entry.
    """
    if not stores.catalog.delete_bike_default(slot, effective_from):
        raise HTTPException(
            status_code=404, detail=f"No {slot.value} default starts on {effective_from}"
        )
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
    changed = backfill_bikes(stores.catalog, dry_run=dry_run)
    bikes = {b.id: b for b in stores.catalog.list_bikes()}
    return BackfillResult(
        dry_run=dry_run,
        changes=[
            BackfillChange(bike=None if key == NO_BIKE else bike_ref(key, bikes), rides=count)
            for key, count in changed.most_common()
        ],
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
    bike = stores.catalog.get_bike(bike_id)
    sent = patch.model_fields_set
    updated = replace(
        bike,
        name=patch.name if patch.name is not None else bike.name,
        kind=patch.kind if "kind" in sent else bike.kind,
        retired=patch.retired if patch.retired is not None else bike.retired,
    )
    stores.catalog.update_bike(updated)
    return bike_out(updated)
