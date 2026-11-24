"""Comparing 2 to 4 rides: their figures side by side, and their samples lined up."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from fitlib.analysis.compare import (
    DEFAULT_POINTS,
    MAX_RIDES,
    MIN_RIDES,
    SMOOTHING_S,
    Aligned,
    NoDistance,
    align,
    has_distance,
)
from fitlib.services.context import RideContext, RideView
from fitlib.services.errors import BadSmoothing, CantAlignByDistance, RideTwice, WrongRideCount
from fitlib.services.rides import find_rides
from fitlib.store.factory import Stores

__all__ = ["DEFAULT_POINTS", "MAX_RIDES", "MIN_RIDES", "SMOOTHING_S", "Compared", "compare"]


def check_count(refs: Sequence[str]) -> None:
    """Check there are enough rides to compare, and not too many.

    Args:
        refs: The rides asked for.

    Raises:
        WrongRideCount: Fewer than ``MIN_RIDES`` or more than ``MAX_RIDES``.
    """
    if not MIN_RIDES <= len(refs) <= MAX_RIDES:
        raise WrongRideCount(MIN_RIDES, MAX_RIDES, len(refs))


def compared_rides(stores: Stores, refs: Sequence[str]) -> list[RideView]:
    """Load the rides to compare, each with its figures and bike.

    Args:
        stores: The library's stores.
        refs: The rides' ids or unique prefixes.

    Returns:
        The rides, in the order given.

    Raises:
        WrongRideCount: Fewer than ``MIN_RIDES`` or more than ``MAX_RIDES``.
        MissingRides: Rides aren't in the library (lists them all).
        RideTwice: The same ride is given twice.
    """
    check_count(refs)
    rides = find_rides(stores.catalog, refs)
    if len({r.id for r in rides}) < len(rides):
        raise RideTwice
    return RideContext.load(stores.catalog).views(rides)


@dataclass(frozen=True)
class Compared:
    """Rides lined up on one axis.

    Attributes:
        views: The rides, with their figures and bikes, in the order given.
        aligned: Their samples on the shared axis, with time gaps when by distance.
        smooth: The smoothing window used, in seconds.
        can_align_distance: Whether every ride recorded distance.
    """

    views: list[RideView]
    aligned: Aligned
    smooth: int
    can_align_distance: bool


def compare(
    stores: Stores,
    refs: Sequence[str],
    by: Literal["time", "distance"] | None = None,
    smooth: int = 0,
    points: int = DEFAULT_POINTS,
) -> Compared:
    """Line rides up on one axis, for overlaid charts and a side-by-side table.

    Args:
        stores: The library's stores.
        refs: The rides, the first being the one time gaps are measured against.
        by: ``time`` or ``distance``; distance when every ride recorded it, if not given.
        smooth: Rolling-average window for power and heart rate, in seconds.
        points: Roughly how many points to return.

    Returns:
        The rides and their lined-up samples.

    Raises:
        WrongRideCount: Fewer than ``MIN_RIDES`` or more than ``MAX_RIDES``.
        BadSmoothing: ``smooth`` isn't one of ``SMOOTHING_S``.
        MissingRides: Rides aren't in the library (lists them all).
        RideTwice: The same ride is given twice.
        CantAlignByDistance: Lining up by distance, and a ride recorded none.
    """
    check_count(refs)
    if smooth not in SMOOTHING_S:
        raise BadSmoothing(SMOOTHING_S, smooth)
    views = compared_rides(stores, refs)
    frames = [stores.streams.get(v.ride.id, v.ride.summary.start) for v in views]
    can_align_distance = all(has_distance(frame) for frame in frames)
    by = by or ("distance" if can_align_distance else "time")
    try:
        aligned = align(frames, by, smooth, points)
    except NoDistance as exc:
        raise CantAlignByDistance(views[exc.index].ride.display_name) from exc
    return Compared(
        views=views, aligned=aligned, smooth=smooth, can_align_distance=can_align_distance
    )
