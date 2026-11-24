"""Rides: finding, listing, showing, matching, editing and deleting them."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

import polars as pl

from fitlib.analysis import similar as matching
from fitlib.analysis import trends
from fitlib.ingest.normalize import VALUE_COLUMNS
from fitlib.metadata import MetaEdit, apply_edit
from fitlib.metrics.track import Track, ride_track
from fitlib.metrics.zwift import world_by_slug, zwift_world
from fitlib.models import Filters, Page, Ride, SortKey, Source
from fitlib.services import deleting
from fitlib.services.context import RideContext, RideView
from fitlib.services.errors import NothingToChange, UnknownStreamFields, WorldNeedsZwift
from fitlib.store.factory import Stores
from fitlib.store.interfaces import MissingRides, RideCatalog, RideNotFound

# Stream columns a ride's samples can be read in; positions only when asked for.
STREAM_FIELDS = ("active", *VALUE_COLUMNS)
LOCATION_FIELDS = ("lat", "lon")
DEFAULT_STREAM_FIELDS = tuple(f for f in STREAM_FIELDS if f not in LOCATION_FIELDS)


def find_ride(catalog: RideCatalog, ref: str) -> Ride:
    """Load a ride from an id or id prefix.

    Args:
        catalog: The library's catalog.
        ref: A full id or a unique prefix.

    Returns:
        The ride.

    Raises:
        RideNotFound: Nothing matches.
        AmbiguousRideId: The prefix matches several rides.
    """
    return catalog.get_ride(catalog.resolve_id(ref))


def find_rides(catalog: RideCatalog, refs: Iterable[str]) -> list[Ride]:
    """Load several rides from ids or prefixes, reporting every one that's missing at once.

    Args:
        catalog: The library's catalog.
        refs: Full ids or unique prefixes.

    Returns:
        The rides, in order (a ride named twice is there twice).

    Raises:
        MissingRides: Some match no ride; lists them all.
        AmbiguousRideId: A prefix matches several rides.
    """
    found: list[Ride] = []
    missing: list[str] = []
    for ref in refs:
        try:
            found.append(find_ride(catalog, ref))
        except RideNotFound:
            missing.append(ref)
    if missing:
        raise MissingRides(missing)
    return found


def _distinct(rides: Iterable[Ride]) -> list[Ride]:
    """Drop repeats of the same ride, keeping the first.

    Args:
        rides: The rides.

    Returns:
        Each ride once, in order.
    """
    return list({ride.id: ride for ride in rides}.values())


def in_world(filters: Filters, slug: str) -> Filters:
    """Narrow library filters to Zwift rides in one world.

    Some worlds lie on the real city they show, so the source matters: a real ride in London
    starts in London's box too.

    Args:
        filters: The other filters.
        slug: The world's short name.

    Returns:
        The filters, limited to Zwift rides starting in the world.

    Raises:
        UnknownWorld: No world has that name.
        WorldNeedsZwift: The filters ask for another source.
    """
    world = world_by_slug(slug)
    if filters.source not in (None, Source.ZWIFT):
        raise WorldNeedsZwift(filters.source.value)
    return replace(filters, source=Source.ZWIFT, starts_in=world.box)


@dataclass(frozen=True)
class RideList:
    """One page of rides, with what's shown beside each.

    Attributes:
        page: The rides on the page, with how many match in all.
        views: Each ride on the page with its figures and bike, in order.
    """

    page: Page[Ride]
    views: list[RideView]


def list_rides(
    stores: Stores,
    filters: Filters,
    world: str | None = None,
    sort: SortKey = SortKey.START,
    descending: bool = True,
    offset: int = 0,
    limit: int = 50,
) -> RideList:
    """List one page of rides matching every filter.

    Args:
        stores: The library's stores.
        filters: What the rides must match.
        world: Only Zwift rides in this world (by short name).
        sort: What to sort by.
        descending: Largest or newest first.
        offset: Matching rides to skip.
        limit: Most rides to return.

    Returns:
        The page, each ride with its figures and bike.

    Raises:
        UnknownWorld: ``world`` isn't a Zwift world.
        WorldNeedsZwift: ``world`` with a source other than Zwift.
    """
    if world:
        filters = in_world(filters, world)
    catalog = stores.catalog
    page = catalog.search(filters, sort=sort, descending=descending, offset=offset, limit=limit)
    return RideList(page=page, views=RideContext.load(catalog).views(page.items))


def ride_view(stores: Stores, ref: str) -> RideView:
    """Load one ride with its figures and bike.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.

    Returns:
        The ride's view.
    """
    catalog = stores.catalog
    return RideContext.load(catalog).view(find_ride(catalog, ref))


def ride_streams(
    stores: Stores, ref: str, fields: Iterable[str] = (), step: int = 1
) -> tuple[Ride, pl.DataFrame]:
    """Load some of a ride's samples.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.
        fields: Columns wanted, from ``STREAM_FIELDS``; every column but the positions if
            none are given.
        step: Keep every ``step``-th second.

    Returns:
        The ride, and its samples: ``t`` plus the columns wanted, in order, each once.

    Raises:
        UnknownStreamFields: A column isn't one of ``STREAM_FIELDS``.
    """
    wanted = list(fields)
    unknown = [f for f in wanted if f not in STREAM_FIELDS]
    if unknown:
        raise UnknownStreamFields(unknown, STREAM_FIELDS)
    chosen = list(dict.fromkeys(wanted)) or list(DEFAULT_STREAM_FIELDS)
    ride = find_ride(stores.catalog, ref)
    frame = stores.streams.get(ride.id, ride.summary.start).gather_every(step)
    return ride, frame.select("t", *chosen)


@dataclass(frozen=True)
class RideMapData:
    """What a ride's map shows.

    Attributes:
        ride: The ride.
        track: Its simplified route, or ``None`` without positions.
        world: The Zwift world's name, for Zwift rides.
    """

    ride: Ride
    track: Track | None
    world: str | None


def ride_map(stores: Stores, ref: str) -> RideMapData:
    """Load a ride's route for a map, simplified so lines stay within a few metres.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.

    Returns:
        The route and, for Zwift rides, the world.
    """
    ride = find_ride(stores.catalog, ref)
    world = zwift_world(ride.summary)
    track = None
    if ride.summary.has_gps:
        track = ride_track(stores.streams.get(ride.id, ride.summary.start))
    return RideMapData(ride=ride, track=track, world=world.name if world else None)


@dataclass(frozen=True)
class Match:
    """Another ride like this one.

    Attributes:
        view: The other ride, with its figures and bike.
        overlap: By route: the share of this ride's route the other covered, 0 to 1.
        other_overlap: By route: the share of the other's route this ride covered.
        same_route: By route: both overlaps are high enough to count as the same route.
        similarity: By effort: 100 for an identical effort, falling towards 0.
    """

    view: RideView
    overlap: float | None = None
    other_overlap: float | None = None
    same_route: bool | None = None
    similarity: int | None = None


@dataclass(frozen=True)
class Similar:
    """Rides like one ride.

    Attributes:
        ride: The ride.
        has_route: Whether it has a route to match (it recorded positions, and they were
            fingerprinted).
        matches: The closest rides first.
    """

    ride: Ride
    has_route: bool
    matches: list[Match]


def similar(
    stores: Stores, ref: str, kind: Literal["route", "effort"] = "route", limit: int = 10
) -> Similar:
    """Find rides on the same roads, or with a similar effort.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.
        kind: ``route`` or ``effort``.
        limit: The most rides to return.

    Returns:
        The matches, closest first.
    """
    catalog = stores.catalog
    ride = find_ride(catalog, ref)
    context = RideContext.load(catalog)
    if kind == "route":
        matches = [
            Match(
                view=context.view(m.ride),
                overlap=m.overlap,
                other_overlap=m.other_overlap,
                same_route=m.same_route,
            )
            for m in matching.similar_routes(catalog, ride, limit)
        ]
    else:
        matches = [
            Match(view=context.view(m.ride), similarity=m.similarity)
            for m in matching.similar_efforts(catalog, ride, limit)
        ]
    return Similar(ride=ride, has_route=bool(catalog.route_cells(ride.id)), matches=matches)


@dataclass(frozen=True)
class Progress:
    """Every ride on one ride's route.

    Attributes:
        ride: The ride.
        has_route: Whether it has a route to follow.
        views: The rides on its route, itself included, oldest first.
    """

    ride: Ride
    has_route: bool
    views: list[RideView]


def route_progress(stores: Stores, ref: str) -> Progress:
    """List every ride on the same route as one ride, to see progress over time.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.

    Returns:
        The same-route rides, this one included, oldest first.
    """
    catalog = stores.catalog
    ride = find_ride(catalog, ref)
    views = RideContext.load(catalog).views(trends.route_progress(catalog, ride))
    return Progress(ride=ride, has_route=bool(catalog.route_cells(ride.id)), views=views)


def edit_ride(stores: Stores, ref: str, change: MetaEdit) -> Ride:
    """Change what was added to one ride: name, notes, effort, bike or tags.

    Args:
        stores: The library's stores.
        ref: The ride's id or a unique prefix.
        change: The change; parts left as ``KEEP`` stay as they are.

    Returns:
        The ride as it is now.

    Raises:
        BikeNotFound: The bike isn't a bike.
    """
    catalog = stores.catalog
    ride = find_ride(catalog, ref)
    catalog.update_meta(ride.id, apply_edit(ride.meta, change))
    return catalog.get_ride(ride.id)


def edit_rides(stores: Stores, refs: Iterable[str], change: MetaEdit) -> list[Ride]:
    """Make the same change to several rides: all of them change, or none.

    Args:
        stores: The library's stores.
        refs: The rides' ids or unique prefixes.
        change: The change; parts left as ``KEEP`` stay as they are.

    Returns:
        The rides as they are now, each once, in the order first named.

    Raises:
        NothingToChange: The change changes nothing.
        MissingRides: Rides aren't in the library (lists them all; nothing changes).
        BikeNotFound: The bike isn't a bike (nothing changes).
    """
    if change.is_empty:
        raise NothingToChange
    catalog = stores.catalog
    rides = _distinct(find_rides(catalog, refs))
    catalog.update_metas({r.id: apply_edit(r.meta, change) for r in rides})
    return [catalog.get_ride(r.id) for r in rides]


def delete_rides(stores: Stores, refs: Iterable[str], remember: bool = True) -> list[Ride]:
    """Delete rides with their streams and original files in the library: all, or none.

    Args:
        stores: The library's stores.
        refs: The rides' ids or unique prefixes.
        remember: Remember the files as deleted, so importing them again skips them.

    Returns:
        The rides deleted, each once.

    Raises:
        MissingRides: Rides aren't in the library (lists them all; nothing is deleted).
    """
    rides = _distinct(find_rides(stores.catalog, refs))
    return deleting.delete_rides(
        stores.catalog, stores.blobs, stores.streams, [r.id for r in rides], remember=remember
    )
