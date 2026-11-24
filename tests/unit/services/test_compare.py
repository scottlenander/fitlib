"""Comparing rides: the checks on what's asked for, and lining them up."""

from __future__ import annotations

import polars as pl
import pytest

from fitlib.services.compare import compare, compared_rides
from fitlib.services.errors import BadSmoothing, CantAlignByDistance, RideTwice, WrongRideCount
from fitlib.store.interfaces import MissingRides
from tests.unit.conftest import ImportedLibrary

ZWIFT = "2025-08-02-08-29-42.fit"
INDOOR = "garmin_indoor_no_hr.fit"
PAUSE = "garmin_nord_pause_10min.fit"
GONE = "00000000-0000-4000-8000-0000000000aa"


@pytest.mark.parametrize("count", [1, 5])
def test_two_to_four_rides(imported: ImportedLibrary, count: int):
    """Comparing needs 2 to 4 rides.

    Given: Too few or too many ride references.
    Expect: ``WrongRideCount`` saying how many were given.
    """
    refs = [imported.ride(ZWIFT).id] * count

    with pytest.raises(WrongRideCount, match=f"got {count}"):
        compared_rides(imported.stores, refs)


def test_the_same_ride_twice_is_refused(imported: ImportedLibrary):
    """Each compared ride must be different.

    Given: One ride's id twice.
    Expect: ``RideTwice``.
    """
    ride_id = imported.ride(ZWIFT).id

    with pytest.raises(RideTwice):
        compared_rides(imported.stores, [ride_id, ride_id])


def test_missing_rides_are_listed(imported: ImportedLibrary):
    """Rides that aren't there are named together.

    Given: A ride and an id of one that doesn't exist.
    Expect: ``MissingRides`` naming the missing id.
    """
    with pytest.raises(MissingRides) as caught:
        compared_rides(imported.stores, [imported.ride(ZWIFT).id, GONE])

    assert caught.value.refs == [GONE]


def test_only_offered_smoothing(imported: ImportedLibrary):
    """Smoothing must be one of the windows offered.

    Given: A 15 s window.
    Expect: ``BadSmoothing``.
    """
    refs = [imported.ride(ZWIFT).id, imported.ride(PAUSE).id]

    with pytest.raises(BadSmoothing, match="got 15"):
        compare(imported.stores, refs, smooth=15)


def test_distance_by_default_and_time_without_it(imported: ImportedLibrary):
    """Rides with distance line up by it; without it, by time, and distance is refused.

    Given: The Zwift and indoor rides, then the indoor ride with its distance removed.
    Expect: Distance by default at first; then time by default, can't align by distance,
        and asking for distance names the indoor ride.
    """
    zwift, indoor = imported.ride(ZWIFT), imported.ride(INDOOR)
    refs = [zwift.id, indoor.id]

    first = compare(imported.stores, refs)
    frame = imported.streams.get(indoor.id, indoor.summary.start)
    blank = frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("distance"))
    imported.streams.put(indoor.id, indoor.summary.start, blank)
    second = compare(imported.stores, refs)

    assert (first.aligned.align, first.can_align_distance) == ("distance", True)
    assert (second.aligned.align, second.can_align_distance) == ("time", False)
    with pytest.raises(CantAlignByDistance, match=indoor.display_name):
        compare(imported.stores, refs, by="distance")
