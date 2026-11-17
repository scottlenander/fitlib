"""Comparing 2 to 4 rides: their samples lined up by time or distance, and their figures."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from fitlib.analysis.compare import (
    DEFAULT_POINTS,
    MAX_RIDES,
    MIN_RIDES,
    SMOOTHING_S,
    NoDistance,
    align,
    has_distance,
)
from fitlib.analysis.training import training
from fitlib.api.deps import StoresDep
from fitlib.api.routers.rides import find_ride
from fitlib.api.schemas import ComparedRide, Comparison, ride_detail

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("")
def compare(
    stores: StoresDep,
    ids: Annotated[
        list[str], Query(description=f"{MIN_RIDES} to {MAX_RIDES} ride ids or unique prefixes.")
    ] = [],  # noqa: B006
    align_by: Annotated[
        Literal["time", "distance"] | None,
        Query(
            alias="align",
            description="Line rides up by time or distance. Default: distance when every "
            "ride recorded it, otherwise time.",
        ),
    ] = None,
    smooth: Annotated[
        int,
        Query(
            description="Seconds to average power and heart rate over: "
            f"{', '.join(str(s) for s in SMOOTHING_S)}."
        ),
    ] = 0,
    points: Annotated[int, Query(ge=10, le=5000, description="Points along the axis.")] = (
        DEFAULT_POINTS
    ),
) -> Comparison:
    """Line rides up on one axis, for overlaid charts and a side-by-side table.

    Args:
        stores: The library's stores.
        ids: The rides, the first being the one time gaps are measured against.
        align_by: ``time`` or ``distance``; chosen for the rides when not given.
        smooth: Rolling-average window for power and heart rate, in seconds.
        points: Roughly how many points to return.

    Returns:
        The shared axis and each ride's figures, samples and (by distance) time gap.

    Raises:
        HTTPException: 422 for too few or too many rides, the same ride twice, a smoothing
            window not in ``SMOOTHING_S``, or lining up by distance when a ride has none.
            Unknown rides are a 404.
    """
    if not MIN_RIDES <= len(ids) <= MAX_RIDES:
        raise HTTPException(
            status_code=422,
            detail=f"Compare {MIN_RIDES} to {MAX_RIDES} rides; got {len(ids)}",
        )
    if smooth not in SMOOTHING_S:
        raise HTTPException(
            status_code=422,
            detail=f"Smoothing must be one of {list(SMOOTHING_S)} seconds; got {smooth}",
        )
    rides = [find_ride(stores, ref) for ref in ids]
    if len({r.id for r in rides}) < len(rides):
        raise HTTPException(status_code=422, detail="The same ride is asked for more than once")
    frames = [stores.streams.get(r.id, r.summary.start) for r in rides]
    can_align_distance = all(has_distance(frame) for frame in frames)
    by = align_by or ("distance" if can_align_distance else "time")
    try:
        aligned = align(frames, by, smooth, points)
    except NoDistance as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{rides[exc.index].display_name} recorded no distance, so the rides "
            "can't be lined up by it; line them up by time instead",
        ) from exc
    bikes = {b.id: b for b in stores.catalog.list_bikes()}
    history = stores.catalog.athlete_history()
    return Comparison(
        align=aligned.align,
        smooth=smooth,
        can_align_distance=can_align_distance,
        x=aligned.x,
        rides=[
            ComparedRide(
                ride=ride_detail(ride, training(stores.catalog, ride, history), bikes),
                series=series,
                gap=aligned.gap[i] if aligned.gap is not None else None,
            )
            for i, (ride, series) in enumerate(zip(rides, aligned.series, strict=True))
        ],
    )
