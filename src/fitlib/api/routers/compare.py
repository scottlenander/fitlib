"""Comparing 2 to 4 rides: their samples lined up by time or distance, and their figures."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from fitlib.api.deps import StoresDep
from fitlib.api.schemas.compare import ComparedRide, Comparison
from fitlib.api.schemas.rides import ride_detail
from fitlib.services import compare as comparing
from fitlib.services.compare import DEFAULT_POINTS, MAX_RIDES, MIN_RIDES, SMOOTHING_S

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
        ServiceError: A 422 for too few or too many rides, the same ride twice, a smoothing
            window not in ``SMOOTHING_S``, or lining up by distance when a ride has none.
        MissingRides: Unknown rides, a 404 listing them all (``missing``).
    """
    found = comparing.compare(stores, ids, align_by, smooth, points)
    aligned = found.aligned
    return Comparison(
        align=aligned.align,
        smooth=found.smooth,
        can_align_distance=found.can_align_distance,
        x=aligned.x,
        rides=[
            ComparedRide(
                ride=ride_detail(view),
                series=series,
                gap=aligned.gap[i] if aligned.gap is not None else None,
            )
            for i, (view, series) in enumerate(zip(found.views, aligned.series, strict=True))
        ],
    )
