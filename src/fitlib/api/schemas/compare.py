"""Comparing rides."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fitlib.api.schemas.rides import (
    RideDetail,
)


class ComparedRide(BaseModel):
    """One ride in a comparison: its figures and its samples on the shared axis.

    Attributes:
        ride: Everything about the ride, for the side-by-side table.
        series: Each channel the ride recorded (of power, heart_rate, cadence, speed and
            altitude), one value per point of ``Comparison.x``; ``null`` where it has none.
        gap: Lined up by distance only: seconds the ride took to reach each point, minus
            the first ride's. Positive means behind the first ride.
    """

    ride: RideDetail
    series: dict[str, list[float | None]]
    gap: list[float | None] | None


class Comparison(BaseModel):
    """Rides lined up on one axis, for overlaid charts.

    Attributes:
        align: ``time`` (x in seconds from the start) or ``distance`` (x in metres).
        smooth: Seconds power and heart rate were averaged over; 0 for raw samples.
        can_align_distance: Whether every ride recorded distance, so they can be lined up
            by it.
        x: The shared axis.
        rides: The rides, in the order asked for; gaps are measured against the first.
    """

    align: Literal["time", "distance"]
    smooth: int
    can_align_distance: bool
    x: list[float]
    rides: list[ComparedRide]
