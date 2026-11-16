"""Finding rides like a given one: on the same roads, or with a similar effort.

Route matches compare route fingerprints (the ~150 m cells each ride passed through).
Effort matches compare figures that don't depend on FTP: duration, intensity, how steady the
ride was, and the shape of its power (or heart-rate) curve.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from fitlib.metrics.curves import best_at
from fitlib.metrics.route import dilate, overlap
from fitlib.models import Filters, Ride, RideSummary
from fitlib.store.interfaces import CatalogStore

# Both rides cover at least this much of each other's route: the same route.
SAME_ROUTE = 0.70
# The other ride covers at least this much of this ride's route: partly shared.
PARTLY_SHARED = 0.30
# Rides sharing the most cells, scored in detail (the rest share too little to matter).
ROUTE_CANDIDATES = 50

# Durations whose best effort, as a share of the ride's average, describes its shape.
SHAPE_DURATIONS_S = (60, 300, 1200)
# How far apart each feature can be before rides count as "1 unit" different.
DURATION_SCALE = math.log(1.5)  # half as long again
INTENSITY_SCALE = math.log(1.10)  # 10 % more NP (or average HR)
VI_SCALE = 0.10
SHAPE_SCALE = 0.10


@dataclass(frozen=True)
class RouteMatch:
    """Another ride on (some of) the same roads.

    Attributes:
        ride: The other ride.
        overlap: The share of this ride's route the other ride covered, 0 to 1.
        other_overlap: The share of the other ride's route this ride covered, 0 to 1.
        same_route: Both overlaps are at least ``SAME_ROUTE``.
    """

    ride: Ride
    overlap: float
    other_overlap: float
    same_route: bool


@dataclass(frozen=True)
class EffortMatch:
    """Another ride with a similar effort.

    Attributes:
        ride: The other ride.
        similarity: 100 for an identical effort, falling towards 0 as rides differ.
    """

    ride: Ride
    similarity: int


def similar_routes(catalog: CatalogStore, ride: Ride, limit: int = 10) -> list[RouteMatch]:
    """Find rides that covered at least ``PARTLY_SHARED`` of a ride's route.

    Args:
        catalog: The library's catalog.
        ride: The ride to match.
        limit: The most matches to return.

    Returns:
        Matches, same-route ones first, then by overlap, then newest first. Empty when the
        ride has no positions.
    """
    mine = catalog.route_cells(ride.id)
    if not mine:
        return []
    mine_grown = dilate(mine)
    matches = []
    for other_id, _ in catalog.route_candidates(ride.id, ROUTE_CANDIDATES):
        theirs = catalog.route_cells(other_id)
        covered = overlap(mine, dilate(theirs))
        if covered < PARTLY_SHARED:
            continue
        covered_back = overlap(theirs, mine_grown)
        matches.append(
            RouteMatch(
                ride=catalog.get_ride(other_id),
                overlap=covered,
                other_overlap=covered_back,
                same_route=covered >= SAME_ROUTE and covered_back >= SAME_ROUTE,
            )
        )
    matches.sort(key=lambda m: (not m.same_route, -m.overlap, -m.ride.summary.start.timestamp()))
    return matches[:limit]


def effort_features(summary: RideSummary) -> dict[str, float] | None:
    """Describe a ride's effort with figures that don't depend on FTP.

    Rides with power are described by power; rides with heart rate only, by heart rate.

    Args:
        summary: The ride's summary.

    Returns:
        Named features (log duration, log intensity, VI, and best efforts as a share of the
        ride's average), or ``None`` for rides with neither power nor heart rate. Best
        efforts longer than the ride are left out.
    """
    if summary.moving_s <= 0:
        return None
    if summary.has_power and summary.np:
        intensity, curve = summary.np, summary.power_curve
        features = {"vi": summary.vi or 1.0}
    elif summary.has_hr and summary.avg_hr:
        intensity, curve = summary.avg_hr, summary.hr_curve
        features = {}
    else:
        return None
    features["duration"] = math.log(summary.moving_s)
    features["intensity"] = math.log(intensity)
    for seconds in SHAPE_DURATIONS_S:
        best = best_at(curve, seconds)
        if best is not None:
            features[f"shape_{seconds}"] = best / intensity
    return features


_SCALES = {"duration": DURATION_SCALE, "intensity": INTENSITY_SCALE, "vi": VI_SCALE}


def effort_similarity(a: dict[str, float], b: dict[str, float]) -> int:
    """Score how alike two efforts are.

    Args:
        a: One ride's features, from ``effort_features``.
        b: The other ride's features.

    Returns:
        100 for identical features, falling towards 0 (a gap of one scale unit on average
        gives 61, two units 14). Only features both rides have are compared.
    """
    shared = a.keys() & b.keys()
    if not shared:
        return 0
    gaps = [((a[k] - b[k]) / _SCALES.get(k, SHAPE_SCALE)) ** 2 for k in shared]
    distance = math.sqrt(sum(gaps) / len(gaps))
    return round(100 * math.exp(-(distance**2) / 2))


def similar_efforts(catalog: CatalogStore, ride: Ride, limit: int = 10) -> list[EffortMatch]:
    """Find the rides whose effort is most like a ride's.

    Rides with power are compared with rides with power; rides with heart rate only, with
    other rides with heart rate only.

    Args:
        catalog: The library's catalog.
        ride: The ride to match.
        limit: The most matches to return.

    Returns:
        The closest rides, most similar first (ties newest first). Empty when the ride has
        neither power nor heart rate.
    """
    mine = effort_features(ride.summary)
    if mine is None:
        return []
    with_power = bool(ride.summary.has_power and ride.summary.np)
    candidates = catalog.search(Filters(has_power=with_power), limit=max(1, catalog.count()))
    matches = []
    for other in candidates.items:
        if other.id == ride.id:
            continue
        theirs = effort_features(other.summary)
        if theirs is None or ("vi" in theirs) != with_power:
            continue
        matches.append(EffortMatch(ride=other, similarity=effort_similarity(mine, theirs)))
    matches.sort(key=lambda m: (-m.similarity, -m.ride.summary.start.timestamp()))
    return matches[:limit]
