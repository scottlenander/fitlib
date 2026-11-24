"""Rides: the library list with search and filters, one ride's detail, and its streams.

A ride can be named by its full id or by a unique prefix of at least 4 characters, as on
the command line.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from fitlib.api.deps import StoresDep
from fitlib.api.schemas import (
    BulkDelete,
    BulkMetaPatch,
    BulkMetaResult,
    DeleteResult,
    MetaPatch,
    RideDetail,
    RideMap,
    RidePage,
    RouteProgress,
    SimilarRide,
    SimilarRides,
    Streams,
    ride_detail,
    ride_item,
    ride_map,
)
from fitlib.metadata import KEEP, MetaEdit, normalize_tags
from fitlib.models import Filters, SortKey, Source
from fitlib.services import rides
from fitlib.services.rides import STREAM_FIELDS

router = APIRouter(prefix="/rides", tags=["rides"])

MAX_PAGE = 200


def _utc(moment: datetime | None) -> datetime | None:
    """Treat a time without a time zone as UTC.

    Args:
        moment: A time from the query string, if given.

    Returns:
        The time with a time zone, or ``None``.
    """
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


@router.get("")
def list_rides(
    stores: StoresDep,
    q: Annotated[
        str | None, Query(description="Words in name, notes, tags, bike or device.")
    ] = None,
    since: Annotated[
        datetime | None, Query(description="Starting at or after; UTC if no zone.")
    ] = None,
    until: Annotated[datetime | None, Query(description="Starting before; UTC if no zone.")] = None,
    source: Source | None = None,
    indoor: bool | None = None,
    min_duration_s: Annotated[int | None, Query(ge=0, description="Moving time at least.")] = None,
    max_duration_s: Annotated[int | None, Query(ge=0, description="Moving time at most.")] = None,
    has_power: bool | None = None,
    tag: Annotated[list[str], Query(description="Rides having every one of these tags.")] = [],  # noqa: B006
    bike_id: str | None = None,
    has_bike: bool | None = None,
    min_rpe: Annotated[int | None, Query(ge=1, le=10)] = None,
    max_rpe: Annotated[int | None, Query(ge=1, le=10)] = None,
    world: Annotated[
        str | None, Query(description="Zwift rides in this world, e.g. watopia.")
    ] = None,
    sort: SortKey = SortKey.START,
    desc: bool = True,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
) -> RidePage:
    """List rides matching every filter given, a page at a time.

    Args:
        stores: The library's stores.
        q: Words to search for.
        since: Earliest start.
        until: Latest start (exclusive).
        source: Only rides from this source.
        indoor: Only indoor (true) or outdoor (false) rides.
        min_duration_s: Shortest moving time.
        max_duration_s: Longest moving time.
        has_power: Only rides with (or without) power.
        tag: Tags every ride must have.
        bike_id: Only rides on this bike.
        has_bike: Only rides with (or without) a bike.
        min_rpe: Lowest perceived effort.
        max_rpe: Highest perceived effort.
        world: Only Zwift rides in this world (by short name).
        sort: What to sort by.
        desc: Largest or newest first.
        offset: Matching rides to skip.
        limit: Most rides to return.

    Returns:
        The page of rides, with the total that match.

    Raises:
        UnknownWorld: ``world`` isn't a Zwift world (a 422).
        WorldNeedsZwift: ``world`` with a source other than Zwift (a 422).
    """
    filters = Filters(
        text=q,
        since=_utc(since),
        until=_utc(until),
        source=source,
        indoor=indoor,
        min_duration_s=min_duration_s,
        max_duration_s=max_duration_s,
        has_power=has_power,
        tags=normalize_tags(tag),
        bike_id=bike_id,
        has_bike=has_bike,
        min_rpe=min_rpe,
        max_rpe=max_rpe,
    )
    found = rides.list_rides(stores, filters, world, sort, desc, offset, limit)
    return RidePage(
        items=[ride_item(view) for view in found.views],
        total=found.page.total,
        offset=found.page.offset,
        limit=found.page.limit,
    )


@router.get("/{ref}")
def get_ride(stores: StoresDep, ref: str) -> RideDetail:
    """Show everything about one ride.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.

    Returns:
        The ride's summary, training figures, zones, curves, laps and metadata.
    """
    return ride_detail(rides.ride_view(stores, ref))


@router.get("/{ref}/streams")
def get_streams(
    stores: StoresDep,
    ref: str,
    fields: Annotated[
        list[str],
        Query(
            description="Columns to return. Default: every column except lat and lon, which "
            f"are only sent when asked for. Any of: {', '.join(STREAM_FIELDS)}."
        ),
    ] = [],  # noqa: B006
    step: Annotated[int, Query(ge=1, le=3600, description="Seconds between samples.")] = 1,
) -> Streams:
    """Return a ride's samples as columns.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.
        fields: Columns to return.
        step: Return every ``step``-th second.

    Returns:
        The time column and each requested column.

    Raises:
        UnknownStreamFields: A field isn't one of ``STREAM_FIELDS`` (a 422).
    """
    ride, frame = rides.ride_streams(stores, ref, fields, step)
    return Streams(
        ride_id=ride.id,
        step=step,
        t=frame["t"].to_list(),
        columns={f: frame[f].to_list() for f in frame.columns if f != "t"},
    )


@router.get("/{ref}/map")
def get_map(stores: StoresDep, ref: str) -> RideMap:
    """A ride's route for a map, simplified so lines stay within a few metres.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.

    Returns:
        The route's points with their times and distances, and its bounds; no points for a
        ride without positions. Zwift rides name their world.
    """
    found = rides.ride_map(stores, ref)
    return ride_map(found.ride.id, found.track, found.world)


@router.get("/{ref}/similar")
def get_similar(
    stores: StoresDep,
    ref: str,
    kind: Literal["route", "effort"] = "route",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SimilarRides:
    """Find rides on the same roads, or with a similar effort.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.
        kind: ``route`` or ``effort``.
        limit: The most rides to return.

    Returns:
        The matches, with their overlap or similarity.
    """
    found = rides.similar(stores, ref, kind, limit)
    return SimilarRides(
        kind=kind,
        has_route=found.has_route,
        items=[
            SimilarRide(
                ride=ride_item(m.view),
                overlap=round(m.overlap, 3) if m.overlap is not None else None,
                other_overlap=round(m.other_overlap, 3) if m.other_overlap is not None else None,
                same_route=m.same_route,
                similarity=m.similarity,
            )
            for m in found.matches
        ],
    )


@router.get("/{ref}/route-progress")
def get_route_progress(stores: StoresDep, ref: str) -> RouteProgress:
    """List every ride on the same route as this one, to see progress over time.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.

    Returns:
        The same-route rides, this one included, oldest first, with TSS.
    """
    found = rides.route_progress(stores, ref)
    return RouteProgress(has_route=found.has_route, items=[ride_item(view) for view in found.views])


@router.patch("/{ref}/meta")
def update_meta(stores: StoresDep, ref: str, patch: MetaPatch) -> RideDetail:
    """Change a ride's name, notes, effort, bike or tags.

    Fields left out of the body stay as they are; ``null`` clears one. A bike chosen here
    counts as set by hand, so default-bike backfills leave it alone.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.
        patch: The changes.

    Returns:
        The updated ride.

    Raises:
        BikeNotFound: ``bike_id`` isn't a bike (a 404).
        InvalidTag: A tag is empty, too long or has a comma (a 422).
    """
    sent = patch.model_fields_set
    change = MetaEdit(
        name=patch.name if "name" in sent else KEEP,
        notes=patch.notes if "notes" in sent else KEEP,
        rpe=patch.rpe if "rpe" in sent else KEEP,
        bike_id=patch.bike_id if "bike_id" in sent else KEEP,
        tags=normalize_tags(patch.tags or ()) if "tags" in sent else KEEP,
    )
    ride = rides.edit_ride(stores, ref, change)
    return ride_detail(rides.ride_view(stores, ride.id))


@router.post("/bulk-meta")
def update_many(stores: StoresDep, patch: BulkMetaPatch) -> BulkMetaResult:
    """Change the effort, bike or tags of several rides at once.

    All the rides change, or none: an unknown ride or bike changes nothing.

    Args:
        stores: The library's stores.
        patch: The rides and the change.

    Returns:
        How many rides changed (each ride once, however often it was named).

    Raises:
        NothingToChange: The patch changes nothing (a 422).
        MissingRides: Rides aren't in the library (a 404 listing them).
        BikeNotFound: ``bike_id`` isn't a bike (a 404).
        InvalidTag: A tag is empty, too long or has a comma (a 422).
    """
    sent = patch.model_fields_set
    change = MetaEdit(
        rpe=patch.rpe if "rpe" in sent else KEEP,
        bike_id=patch.bike_id if "bike_id" in sent else KEEP,
        add_tags=normalize_tags(patch.add_tags),
        remove_tags=normalize_tags(patch.remove_tags),
    )
    return BulkMetaResult(updated=len(rides.edit_rides(stores, patch.ids, change)))


@router.delete("/{ref}")
def delete_ride(stores: StoresDep, ref: str) -> DeleteResult:
    """Delete a ride, with its stream and original file in the library.

    Your own copy of the file is kept. Importing it again skips it unless asked to include
    deleted rides.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.

    Returns:
        One ride deleted.
    """
    # Found on its own first, so a missing ride is the single-ride 404.
    ride = rides.find_ride(stores.catalog, ref)
    rides.delete_rides(stores, [ride.id])
    return DeleteResult(deleted=1)


@router.post("/bulk-delete")
def delete_many(stores: StoresDep, body: BulkDelete) -> DeleteResult:
    """Delete several rides at once, all or none.

    Args:
        stores: The library's stores.
        body: The rides.

    Returns:
        How many rides were deleted (each ride once, however often it was named).

    Raises:
        MissingRides: Rides aren't in the library (a 404 listing them); nothing is deleted.
    """
    return DeleteResult(deleted=len(rides.delete_rides(stores, body.ids)))
