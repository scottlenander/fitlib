"""Rides: the library list with search and filters, one ride's detail, and its streams.

A ride can be named by its full id or by a unique prefix of at least 4 characters, as on
the command line.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from fitlib.analysis.training import training
from fitlib.api.deps import StoresDep
from fitlib.api.schemas import (
    MetaPatch,
    RideDetail,
    RidePage,
    Streams,
    ride_detail,
    ride_item,
)
from fitlib.ingest.normalize import VALUE_COLUMNS
from fitlib.metadata import normalize_tag
from fitlib.models import Filters, Ride, RideMeta, SortKey, Source
from fitlib.store.factory import Stores

router = APIRouter(prefix="/rides", tags=["rides"])

MAX_PAGE = 200
STREAM_FIELDS = ("active", *VALUE_COLUMNS)
LOCATION_FIELDS = ("lat", "lon")
DEFAULT_STREAM_FIELDS = tuple(f for f in STREAM_FIELDS if f not in LOCATION_FIELDS)


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


def find_ride(stores: Stores, ref: str) -> Ride:
    """Load a ride from an id or id prefix.

    Args:
        stores: The library's stores.
        ref: A full id or a unique prefix.

    Returns:
        The ride.

    Raises:
        RideNotFound: Nothing matches (a 404).
        AmbiguousRideId: The prefix matches several rides (a 409 listing them).
    """
    return stores.catalog.get_ride(stores.catalog.resolve_id(ref))


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
        sort: What to sort by.
        desc: Largest or newest first.
        offset: Matching rides to skip.
        limit: Most rides to return.

    Returns:
        The page of rides, with the total that match.
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
        tags=tuple(dict.fromkeys(normalize_tag(t) for t in tag)),
        bike_id=bike_id,
        has_bike=has_bike,
        min_rpe=min_rpe,
        max_rpe=max_rpe,
    )
    catalog = stores.catalog
    page = catalog.search(filters, sort=sort, descending=desc, offset=offset, limit=limit)
    history = catalog.athlete_history()
    bikes = {b.id: b for b in catalog.list_bikes()}
    return RidePage(
        items=[ride_item(r, training(catalog, r, history), bikes) for r in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
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
    ride = find_ride(stores, ref)
    bikes = {b.id: b for b in stores.catalog.list_bikes()}
    return ride_detail(ride, training(stores.catalog, ride), bikes)


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
        HTTPException: 422 if a field isn't one of ``STREAM_FIELDS``.
    """
    unknown = [f for f in fields if f not in STREAM_FIELDS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown stream fields {unknown}; expected any of {list(STREAM_FIELDS)}",
        )
    chosen = list(dict.fromkeys(fields)) or list(DEFAULT_STREAM_FIELDS)
    ride = find_ride(stores, ref)
    frame = stores.streams.get(ride.id, ride.summary.start).gather_every(step)
    return Streams(
        ride_id=ride.id,
        step=step,
        t=frame["t"].to_list(),
        columns={f: frame[f].to_list() for f in chosen},
    )


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
    catalog = stores.catalog
    ride = find_ride(stores, ref)
    sent = patch.model_fields_set
    m = ride.meta
    if "bike_id" in sent and patch.bike_id is not None:
        catalog.get_bike(patch.bike_id)
    tags = m.tags
    if "tags" in sent:
        tags = tuple(dict.fromkeys(normalize_tag(t) for t in patch.tags or ()))
    meta = RideMeta(
        name=patch.name if "name" in sent else m.name,
        notes=patch.notes if "notes" in sent else m.notes,
        rpe=patch.rpe if "rpe" in sent else m.rpe,
        bike_id=patch.bike_id if "bike_id" in sent else m.bike_id,
        tags=tags,
        # A bike chosen here is the user's; otherwise keep where the bike came from.
        bike_from_default=m.bike_from_default and "bike_id" not in sent,
    )
    catalog.update_meta(ride.id, meta)
    return get_ride(stores, ride.id)
