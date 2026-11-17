"""Finding similar rides: by route (shared cells) and by effort (FTP-independent figures)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from fitlib.analysis.similar import (
    effort_features,
    effort_similarity,
    similar_efforts,
    similar_routes,
)
from fitlib.ingest.normalize import to_frame
from fitlib.metrics import basic
from fitlib.metrics.curves import best_averages
from fitlib.metrics.power import normalized_power, variability_index
from fitlib.metrics.route import encode
from fitlib.models import Ride, Route
from fitlib.store.memory import MemoryCatalog
from tests.unit.factories import DEFAULT_START, make_ride, make_summary

# One cell is about 150 m north to south; this steps exactly one cell.
CELL_LAT = 180 / (1 << 17)


def road(start: int, cells: int, row_offset: int = 0) -> Route:
    """A straight road heading north near Roubaix, as route cells.

    Args:
        start: How many cells north of the origin the road starts.
        cells: How many cells it runs through.
        row_offset: Shift every point this many cells east, as GPS drift would.

    Returns:
        The road's cells.
    """
    lat0, lon0 = 50.30, 3.40 + row_offset * 360 / (1 << 18)
    return frozenset(encode(lat0 + (start + i + 0.5) * CELL_LAT, lon0) for i in range(cells))


def add(catalog: MemoryCatalog, day: int, route: Route = frozenset(), **summary) -> Ride:
    """Add a ride on a given day with a route.

    Args:
        catalog: The catalog to add it to.
        day: Days after 2 Aug 2025.
        route: Its cells.
        **summary: ``RideSummary`` fields to change.

    Returns:
        The ride.
    """
    ride = make_ride(start=DEFAULT_START + timedelta(days=day), **summary)
    catalog.add_ride(ride, route=route)
    return ride


# -- routes -----------------------------------------------------------------------------------


def test_identical_and_drifted_routes_are_the_same_route():
    """Rides on the same road match fully, even when GPS drift moves them one cell over.

    Given: a 20-cell road, the same road again, and the road shifted one cell east.
    Expect: both match at 100 % both ways and count as the same route.
    """
    catalog = MemoryCatalog()
    mine = add(catalog, 0, road(0, 20))
    again = add(catalog, 1, road(0, 20))
    drifted = add(catalog, 2, road(0, 20, row_offset=1) | road(0, 1))

    matches = similar_routes(catalog, mine)

    assert {m.ride.id for m in matches} == {again.id, drifted.id}
    for match in matches:
        assert (match.overlap, match.other_overlap) == (1.0, 1.0)
        assert match.same_route


def test_partly_shared_route():
    """A ride covering half of this route, and as much elsewhere, is partly shared.

    Given: a 20-cell road, and a ride on its first 10 cells plus 10 cells far to the north.
    Expect: one match, not the same route: the other ride covers 11 of this ride's 20 cells
    (its 10, plus the one next to where it turns off, within drift tolerance), and this ride
    covers 10 of its 20.
    """
    catalog = MemoryCatalog()
    mine = add(catalog, 0, road(0, 20))
    half = add(catalog, 1, road(0, 10) | road(100, 10))

    [match] = similar_routes(catalog, mine)

    assert match.ride.id == half.id
    assert match.overlap == pytest.approx(0.55)
    assert match.other_overlap == pytest.approx(0.5)
    assert not match.same_route, "half the route is not the same route"


def test_a_short_ride_inside_a_long_one_is_one_sided():
    """A short ride entirely on a long ride's route covers little of the long one.

    Given: a 60-cell road and a ride on 10 of its cells.
    Expect: from the long ride, 12 cells (the 10 plus one either end, within drift
    tolerance) is 20 %, too little to list; from the short ride, the long one covers 100 % of
    it but it covers only 20 % back, so it's partly shared.
    """
    catalog = MemoryCatalog()
    long_ride = add(catalog, 0, road(0, 60))
    short_ride = add(catalog, 1, road(10, 10))

    from_long = similar_routes(catalog, long_ride)
    [from_short] = similar_routes(catalog, short_ride)

    assert from_long == [], "20 % of the long route is under the 30 % threshold"
    assert (from_short.overlap, from_short.other_overlap) == (1.0, 0.2)
    assert not from_short.same_route


def test_same_routes_first_then_overlap_then_newest():
    """Same-route rides come first, then partly shared by overlap; ties go newest first.

    Given: a 20-cell road; two rides on all of it (days 1 and 2) and one on 60 % of it.
    Expect: the newer full ride, the older full ride, then the partial one; a limit of 1
    keeps only the first.
    """
    catalog = MemoryCatalog()
    mine = add(catalog, 0, road(0, 20))
    older = add(catalog, 1, road(0, 20))
    newer = add(catalog, 2, road(0, 20))
    partial = add(catalog, 3, road(0, 12))

    matches = similar_routes(catalog, mine)
    first = similar_routes(catalog, mine, limit=1)

    assert [m.ride.id for m in matches] == [newer.id, older.id, partial.id]
    assert [m.ride.id for m in first] == [newer.id]


def test_rides_without_positions_have_no_route_matches():
    """An indoor ride without GPS has nothing to match on.

    Given: a ride with no cells, and another ride with a route.
    Expect: no matches.
    """
    catalog = MemoryCatalog()
    indoor = add(catalog, 0)
    add(catalog, 1, road(0, 20))

    assert similar_routes(catalog, indoor) == []


# -- efforts ----------------------------------------------------------------------------------


def test_effort_similarity_scale():
    """Similarity is 100 for identical efforts and falls with the gap between them.

    Given: identical features, features one scale unit apart in every shared feature, and
    features with nothing in common.
    Expect: 100, 61 and 0.
    """
    a = {"duration": 0.0, "intensity": 0.0}
    one_unit = {"duration": 0.405465, "intensity": 0.0953102}

    assert effort_similarity(a, a) == 100
    assert effort_similarity(a, one_unit) == 61
    assert effort_similarity(a, {"vi": 1.0}) == 0


def test_effort_features_use_power_or_heart_rate():
    """Rides with power are described by power; heart-rate-only rides by heart rate.

    Given: the factory ride (power and HR), the same without power, and one with neither.
    Expect: VI and power shape for the first; no VI for the HR-only ride; nothing for the
    last. Best efforts longer than a 10-minute ride are left out.
    """
    with_power = effort_features(make_ride().summary)
    hr_only = effort_features(make_ride(has_power=False, np=None).summary)
    nothing = effort_features(make_ride(has_power=False, np=None, has_hr=False).summary)
    short = effort_features(make_ride(moving_s=600, power_curve=((60, 380.0),)).summary)

    assert with_power is not None and "vi" in with_power
    assert with_power["shape_1200"] == pytest.approx(250 / 215)
    assert hr_only is not None and "vi" not in hr_only
    assert hr_only["shape_1200"] == pytest.approx(155 / 142)
    assert nothing is None
    assert short is not None and set(short) == {"vi", "duration", "intensity", "shape_60"}


def test_similar_efforts_rank_closest_first_and_keep_power_apart_from_hr():
    """The closest efforts come first; rides with power are never matched with HR-only ones.

    Given: a 1-hour ride at 215 W NP; the same effort, one 5 % harder, one half as long and
    much harder, and an HR-only ride.
    Expect: the same effort (100), then the slightly harder one, then the very different
    one; no HR-only ride.
    """
    catalog = MemoryCatalog()
    mine = add(catalog, 0)
    same = add(catalog, 1)
    harder = add(catalog, 2, np=225.75)
    different = add(catalog, 3, moving_s=1750, np=280.0, vi=1.25)
    add(catalog, 4, has_power=False, np=None)

    matches = similar_efforts(catalog, mine)

    assert [m.ride.id for m in matches] == [same.id, harder.id, different.id]
    assert matches[0].similarity == 100
    assert matches[1].similarity > matches[2].similarity


def test_similar_efforts_for_a_ride_without_data():
    """A ride with neither power nor heart rate has no effort matches.

    Given: such a ride, and an ordinary ride.
    Expect: no matches.
    """
    catalog = MemoryCatalog()
    blank = add(catalog, 0, has_power=False, np=None, has_hr=False)
    add(catalog, 1)

    assert similar_efforts(catalog, blank) == []


def summary_of(frame: pl.DataFrame) -> dict:
    """Work out the summary figures effort matching uses, from a ride's samples.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        ``RideSummary`` fields: moving time, NP, VI and the power curve.
    """
    np = normalized_power(frame)
    return {
        "moving_s": basic.moving_s(frame),
        "np": np,
        "vi": variability_index(np, basic.avg_power(frame)),
        "power_curve": best_averages(frame, "power"),
    }


def test_a_one_minute_stop_still_counts_as_a_similar_effort():
    """Standing still for a minute, with the timer running, barely changes the score.

    Given: an hour at 10 m/s alternating 180 W and 220 W each minute, and the same hour with
        a 60 s stop at 0 W after 25 minutes (before its best 20 minutes).
    Expect: a similarity of at least 95.
    """
    start = datetime(2025, 8, 2, 6, 30, tzinfo=UTC)

    def sample(i: int, moving: bool) -> dict:
        """One second of riding (or standing still).

        Args:
            i: Seconds from the start.
            moving: Whether the rider is moving.

        Returns:
            The record.
        """
        watts = 180 if (i // 60) % 2 else 220
        return {
            "timestamp": start + timedelta(seconds=i),
            "speed": 10.0 if moving else 0.0,
            "power": watts if moving else 0,
        }

    steady = to_frame([sample(i, True) for i in range(3600)])
    stopped = to_frame([sample(i, not 1500 <= i < 1560) for i in range(3660)])

    a = effort_features(make_summary(**summary_of(steady)))
    b = effort_features(make_summary(**summary_of(stopped)))

    assert a is not None and b is not None
    assert effort_similarity(a, b) >= 95
