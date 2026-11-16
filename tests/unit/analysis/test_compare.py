"""Lining rides up by time or distance, smoothing, and the time gap between them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from fitlib.analysis.compare import NoDistance, align, align_distance, align_time, smooth
from fitlib.ingest.normalize import to_frame

START = datetime(2025, 8, 2, 6, 30, tzinfo=UTC)


def ride(speeds: list[float], power: int = 200) -> pl.DataFrame:
    """Build a ride from one speed per second, with steady power while moving.

    Args:
        speeds: Metres per second, one per second; 0 is standing still (and 0 W).
        power: Watts while moving.

    Returns:
        The 1 Hz frame, with distance adding up the speeds.
    """
    rows, distance = [], 0.0
    for i, speed in enumerate(speeds):
        rows.append(
            {
                "timestamp": START + timedelta(seconds=i),
                "speed": speed,
                "distance": distance,
                "power": power if speed else 0,
            }
        )
        distance += speed
    return to_frame(rows)


def test_time_alignment_shares_one_axis_and_ends_short_rides_early():
    """Rides line up second for second, sampled to about the points asked for.

    Given: a 100 s ride and a 60 s ride, aligned by time with 50 points.
    Expect: an axis every 2 s to 98 s, and the short ride's values empty after 58 s.
    """
    long, short = ride([10.0] * 100), ride([5.0] * 60, power=150)

    aligned = align_time([long, short], points=50)

    assert aligned.align == "time"
    assert aligned.x == [float(t) for t in range(0, 100, 2)]
    assert aligned.gap is None, "should have no time gap when lined up by time"
    assert aligned.series[0]["power"] == [200] * 50
    assert aligned.series[1]["power"] == [150] * 30 + [None] * 20, (
        "should be empty after the short ride ends"
    )


def test_distance_alignment_matches_points_on_the_road():
    """Rides line up by metres ridden, up to the shortest ride's distance.

    Given: one ride at 10 m/s for 100 s (990 m) and one at 5 m/s for 300 s.
    Expect: an axis from 0 to 990 m; at 500 m the slow ride is 50 s behind.
    """
    fast, slow = ride([10.0] * 100), ride([5.0] * 300, power=150)

    aligned = align_distance([fast, slow], points=100)

    assert aligned.x[0] == 0 and aligned.x[-1] == 990
    assert len(aligned.x) == 100
    half = aligned.x.index(500.0)
    assert aligned.gap is not None
    assert aligned.gap[0][half] == 0, "should measure the first ride against itself"
    assert aligned.gap[1][half] == 50
    assert set(aligned.series[1]["power"]) == {150}


def test_a_one_minute_stop_shows_as_a_60_second_step_in_the_gap():
    """A stop puts a ride a minute behind from that point on, and not before it.

    Given: two rides at 10 m/s for 1000 m, the second standing still for 60 s at 500 m.
    Expect: no gap before 500 m and a 60 s gap after it.
    """
    steady = ride([10.0] * 101)
    stopped = ride([10.0] * 50 + [0.0] * 60 + [10.0] * 51)

    aligned = align_distance([steady, stopped], points=101)

    assert aligned.gap is not None
    gap = dict(zip(aligned.x, aligned.gap[1], strict=True))
    assert gap[400.0] == 0
    assert gap[490.0] == 0, "should not count the stop before reaching it"
    assert gap[510.0] == 60
    assert gap[1000.0] == 60


def test_distance_alignment_needs_distance_on_every_ride():
    """A ride without distance can't be lined up by it, and the error says which.

    Given: a ride with distance and a trainer ride with power only.
    Expect: NoDistance naming the second ride; time alignment still works.
    """
    outdoor = ride([10.0] * 60)
    trainer = to_frame(
        [{"timestamp": START + timedelta(seconds=i), "power": 180} for i in range(60)]
    )

    with pytest.raises(NoDistance) as raised:
        align([outdoor, trainer], by="distance")

    assert raised.value.index == 1
    assert "Ride 2" in str(raised.value)
    assert align([outdoor, trainer], by="time").series[1]["power"][0] == 180


def test_smoothing_flattens_spikes_but_keeps_steady_power_and_gaps():
    """Smoothing averages power over a window without filling pauses.

    Given: 30 s at 200 W with a one-second 1200 W spike, then a pause, then 200 W.
    Expect: steady seconds stay 200 W, the spike falls below 400 W, and the pause stays empty.
    """
    rows = [{"timestamp": START + timedelta(seconds=i), "power": 200} for i in range(30)]
    rows[15]["power"] = 1200
    rows += [{"timestamp": START + timedelta(seconds=60 + i), "power": 200} for i in range(30)]
    frame = to_frame(rows)

    smoothed = smooth(frame, 10)["power"]

    assert smoothed[2] == 200
    assert smoothed[15] is not None and smoothed[15] < 400, "should flatten a one-second spike"
    assert smoothed[45] is None, "should leave the pause empty"
    assert smoothed[75] == 200
    assert smooth(frame, 0)["power"].to_list() == frame["power"].to_list(), (
        "should leave power alone with smoothing off"
    )


def test_channels_a_ride_did_not_record_are_left_out():
    """Only recorded channels are returned for each ride.

    Given: rides with speed and power but no heart rate or cadence.
    Expect: power and speed in each ride's series, no heart rate.
    """
    aligned = align([ride([8.0] * 40), ride([9.0] * 40)], by="time")

    assert set(aligned.series[0]) == {"power", "speed"}
