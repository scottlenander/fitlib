"""A ride's track for drawing on a map: its positions, simplified to a few thousand points.

Simplified with Douglas–Peucker on a local flat projection: points are dropped while the line
stays within a few metres of the original, so straight roads take a handful of points and
bends keep theirs. Each kept point keeps its time and distance, so the map can show where a
moment of the ride was.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl

EARTH_RADIUS_M = 6_371_000.0
# How far the simplified line may stray from the recorded one.
TOLERANCE_M = 3.0
# The most points sent for one ride; the tolerance grows until the track fits.
MAX_POINTS = 2_000


@dataclass(frozen=True)
class TrackPoint:
    """One point of a track.

    Attributes:
        t: Seconds from the start.
        lat: Latitude, degrees.
        lon: Longitude, degrees.
        distance_m: Distance ridden by then, if recorded.
    """

    t: int
    lat: float
    lon: float
    distance_m: float | None


@dataclass(frozen=True)
class Track:
    """A simplified track.

    Attributes:
        points: The kept points, in order; the first and last recorded ones always.
        bounds: ``(south, west, north, east)`` around every recorded position.
        start_finish_m: How far apart the first and last positions are.
    """

    points: tuple[TrackPoint, ...]
    bounds: tuple[float, float, float, float]
    start_finish_m: float


def _project(lat: list[float], lon: list[float]) -> tuple[list[float], list[float]]:
    """Project positions to metres on a plane through their mean latitude.

    Plenty accurate over a ride's few tens of kilometres.

    Args:
        lat: Latitudes, degrees.
        lon: Longitudes, degrees.

    Returns:
        x (east) and y (north) in metres.
    """
    scale = math.cos(math.radians(sum(lat) / len(lat))) * EARTH_RADIUS_M
    x = [math.radians(v) * scale for v in lon]
    y = [math.radians(v) * EARTH_RADIUS_M for v in lat]
    return x, y


def simplify(x: Sequence[float], y: Sequence[float], tolerance: float) -> list[int]:
    """Pick the points Douglas–Peucker keeps.

    Args:
        x: Projected x of every point, metres.
        y: Projected y, metres.
        tolerance: How far the simplified line may stray, metres.

    Returns:
        The kept points' indexes, ascending; always the first and last.
    """
    n = len(x)
    if n <= 2:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        x0, y0 = x[first], y[first]
        dx, dy = x[last] - x0, y[last] - y0
        length = math.hypot(dx, dy)
        far, far_dist = first, -1.0
        for i in range(first + 1, last):
            px, py = x[i] - x0, y[i] - y0
            # A loop's ends meet: measure from the shared point instead of a line.
            dist = abs(dx * py - dy * px) / length if length else math.hypot(px, py)
            if dist > far_dist:
                far, far_dist = i, dist
        if far_dist > tolerance:
            keep[far] = True
            stack += [(first, far), (far, last)]
    return [i for i, kept in enumerate(keep) if kept]


def ride_track(
    frame: pl.DataFrame, tolerance_m: float = TOLERANCE_M, max_points: int = MAX_POINTS
) -> Track | None:
    """Simplify a ride's positions for a map.

    Args:
        frame: The ride's 1 Hz stream (``t``, ``lat``, ``lon``, ``distance``).
        tolerance_m: How far the simplified line may stray from the recorded one, to start.
        max_points: The most points to return; the tolerance doubles until they fit.

    Returns:
        The track, or ``None`` if the ride recorded no positions.
    """
    located = frame.select("t", "lat", "lon", "distance").drop_nulls(["lat", "lon"])
    if located.is_empty():
        return None
    lat: list[float] = located["lat"].to_list()
    lon: list[float] = located["lon"].to_list()
    x, y = _project(lat, lon)
    tolerance = tolerance_m
    kept = simplify(x, y, tolerance)
    while len(kept) > max_points:
        tolerance *= 2
        kept = simplify(x, y, tolerance)
    t = located["t"].to_list()
    distance = located["distance"].to_list()
    points = tuple(
        TrackPoint(
            t=int(t[i]),
            lat=round(float(lat[i]), 6),
            lon=round(float(lon[i]), 6),
            distance_m=None if distance[i] is None else round(float(distance[i]), 1),
        )
        for i in kept
    )
    # Rounded like the points, so every point lies inside.
    bounds = (round(min(lat), 6), round(min(lon), 6), round(max(lat), 6), round(max(lon), 6))
    gap = math.hypot(x[-1] - x[0], y[-1] - y[0])
    return Track(points=points, bounds=bounds, start_finish_m=round(gap, 1))
