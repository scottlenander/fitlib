"""Comparing rides: samples lined up by time or distance, figures side by side."""

from __future__ import annotations

import polars as pl
import pytest

from fitlib.store.factory import open_stores
from tests.api.conftest import Api

EXPORT_A = "garmin_export.zip:garmin_export_ride_a.fit"
EXPORT_B = "garmin_export.zip:garmin_export_ride_b.fit"
ZWIFT = "zwift_watopia_steady_60min.fit"
INTERVALS = "garmin_nord_intervals_5x4.fit"
INDOOR = "garmin_indoor_no_hr.fit"
HR_ONLY = "garmin_nord_hr_no_power.fit"


def compare(api: Api, *files: str, **params) -> dict:
    """Ask the API to compare fixture rides, expecting success.

    Args:
        api: The client and its ride ids.
        *files: The fixture files of the rides, in order.
        **params: Other query parameters, e.g. ``align="time"``.

    Returns:
        The comparison.
    """
    response = api.client.get("/api/compare", params={"ids": [api.ids[f] for f in files], **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_rides_with_distance_line_up_by_distance_by_default(reader: Api):
    """Rides that all recorded distance are lined up by it, with time gaps to the first.

    Given: the two exported rides.
    Expect: distance alignment from 0 m, both rides' figures in order, and a gap for each
    ride that starts at 0 and is all 0 for the first ride.
    """
    body = compare(reader, EXPORT_A, EXPORT_B)

    assert (body["align"], body["can_align_distance"], body["smooth"]) == ("distance", True, 0)
    assert body["x"][0] == 0
    assert len(body["x"]) == 1500
    assert [r["ride"]["id"] for r in body["rides"]] == [
        reader.ids[EXPORT_A],
        reader.ids[EXPORT_B],
    ]
    first, second = body["rides"]
    assert set(first["gap"]) == {0}, "should measure the first ride against itself"
    assert second["gap"][0] == 0
    assert len(second["series"]["power"]) == len(body["x"])
    assert first["ride"]["training"]["tss"] is not None, "should carry the ride's full figures"


def test_time_alignment_has_no_gap_and_covers_the_longest_ride(reader: Api):
    """Lined up by time, the axis runs to the end of the longest ride.

    Given: the 60-minute Zwift ride and the 30-minute indoor ride, by time with 600 points.
    Expect: an axis to just under 3600 s; the indoor ride's power ends halfway; no gaps.
    """
    body = compare(reader, ZWIFT, INDOOR, align="time", points=600)

    assert body["align"] == "time"
    assert body["x"][-1] == 3594
    zwift, indoor = body["rides"]
    assert zwift["gap"] is None and indoor["gap"] is None
    power = indoor["series"]["power"]
    assert power[299] is not None and power[300] is None, "should end after 30 minutes"


def test_four_rides_and_id_prefixes(reader: Api):
    """Up to four rides can be compared, named by unique id prefixes.

    Given: four rides, each by the first 8 characters of its id.
    Expect: all four in order, each with only the channels it recorded.
    """
    files = (INTERVALS, HR_ONLY, ZWIFT, INDOOR)

    response = reader.client.get("/api/compare", params={"ids": [reader.ids[f][:8] for f in files]})

    rides = response.json()["rides"]
    assert response.status_code == 200
    assert [r["ride"]["id"] for r in rides] == [reader.ids[f] for f in files]
    assert "power" not in rides[1]["series"], "should leave out power for the HR-only ride"
    assert "heart_rate" not in rides[3]["series"], "should leave out HR for the no-HR ride"


def test_smoothing_turns_interval_steps_into_ramps(reader: Api):
    """30-second smoothing averages power across the steps between intervals.

    Given: the interval ride (clean steps between a few power levels), raw and smoothed.
    Expect: raw power has only a handful of levels; smoothed power has many more in between.
    """
    raw = compare(reader, INTERVALS, ZWIFT, align="time")
    smoothed = compare(reader, INTERVALS, ZWIFT, align="time", smooth=30)

    def levels(body: dict) -> int:
        """Count the interval ride's different plotted powers.

        Args:
            body: A comparison.

        Returns:
            How many different values its power takes.
        """
        return len({v for v in body["rides"][0]["series"]["power"] if v is not None})

    assert smoothed["smooth"] == 30
    assert levels(raw) <= 5
    assert levels(smoothed) > 20, "should have values between the interval and recovery power"


@pytest.mark.parametrize(
    ("count", "message"),
    [(1, "got 1"), (5, "got 5")],
)
def test_two_to_four_rides(reader: Api, count: int, message: str):
    """Fewer than two or more than four rides is refused.

    Given: 1 or 5 ride ids.
    Expect: a 422 saying how many were given.
    """
    ids = list(reader.ids.values())[:count]

    response = reader.client.get("/api/compare", params={"ids": ids})

    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_only_offered_smoothing_windows(reader: Api):
    """Smoothing is off, 10 s or 30 s; anything else is refused.

    Given: a smoothing window of 20 s.
    Expect: a 422 listing the choices.
    """
    response = reader.client.get(
        "/api/compare", params={"ids": [reader.ids[ZWIFT], reader.ids[INDOOR]], "smooth": 20}
    )

    assert response.status_code == 422
    assert "[0, 10, 30]" in response.json()["detail"]


def test_the_same_ride_twice_is_refused(reader: Api):
    """A ride can't be compared with itself, even named two ways.

    Given: the Zwift ride by full id and by prefix.
    Expect: a 422.
    """
    ride_id = reader.ids[ZWIFT]

    response = reader.client.get("/api/compare", params={"ids": [ride_id, ride_id[:8]]})

    assert response.status_code == 422
    assert "more than once" in response.json()["detail"]


def test_an_unknown_ride_is_not_found(reader: Api):
    """An id that matches no ride is a 404.

    Given: the Zwift ride and an id nobody has.
    Expect: a 404.
    """
    response = reader.client.get(
        "/api/compare", params={"ids": [reader.ids[ZWIFT], "ffffffffffff"]}
    )

    assert response.status_code == 404


def test_rides_without_distance_line_up_by_time(writer: Api):
    """A ride without distance makes time the default, and refuses distance.

    Given: the indoor ride with its distance removed, and the Zwift ride.
    Expect: time alignment by default and can_align_distance false; asking for distance is
    a 422 naming the ride.
    """
    with open_stores(writer.config) as stores:
        ride = stores.catalog.get_ride(writer.ids[INDOOR])
        frame = stores.streams.get(ride.id, ride.summary.start)
        blank = frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("distance"))
        stores.streams.put(ride.id, ride.summary.start, blank)

    body = compare(writer, ZWIFT, INDOOR)
    response = writer.client.get(
        "/api/compare",
        params={"ids": [writer.ids[ZWIFT], writer.ids[INDOOR]], "align": "distance"},
    )

    assert (body["align"], body["can_align_distance"]) == ("time", False)
    assert response.status_code == 422
    assert ride.display_name in response.json()["detail"]
