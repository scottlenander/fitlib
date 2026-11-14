"""Basic ride figures, checked against values worked out from the fixture specs."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from functools import cache
from itertools import pairwise
from statistics import mean

import polars as pl
import pytest

from fitlib.ingest.decoder import decode
from fitlib.ingest.normalize import to_frame
from fitlib.metrics import basic
from tests.fixtures.generate import METRES_PER_DEG_LAT, committed_bytes, samples, speed_for_power
from tests.fixtures.specs import RIDES, RideSpec, ride

CYCLING = [spec for spec in RIDES if spec.sport == "cycling"]


@cache
def frame_for(name: str) -> pl.DataFrame:
    """Decode and normalize a committed fixture ride (cached, as frames are read-only here).

    Args:
        name: The ride spec's name.

    Returns:
        The ride's 1 Hz frame.
    """
    return to_frame(decode(committed_bytes(name)).records)


def synthetic(rows: list[dict]) -> pl.DataFrame:
    """Build a frame from hand-written per-second records starting at 06:30 UTC.

    Args:
        rows: One dict of record fields per second, e.g. ``{"power": 200, "cadence": 90}``.

    Returns:
        The 1 Hz frame.
    """
    start = datetime(2025, 8, 2, 6, 30, tzinfo=UTC)
    return to_frame(
        [{"timestamp": start + timedelta(seconds=i), **row} for i, row in enumerate(rows)]
    )


@pytest.mark.parametrize("spec", CYCLING, ids=lambda s: s.name)
def test_elapsed_and_moving_time(spec: RideSpec):
    """Elapsed time runs start to finish; moving time leaves out pauses.

    Given: each cycling fixture (one has a 10-minute pause; one uses smart recording).
    Expect: elapsed = the spec's riding time plus pauses; moving = the riding time.
    """
    frame = frame_for(spec.name)

    assert basic.elapsed_s(frame) == spec.elapsed_s, "elapsed time includes pauses"
    assert basic.moving_s(frame) == spec.duration_s, "moving time excludes pauses"


@pytest.mark.parametrize("spec", CYCLING, ids=lambda s: s.name)
def test_power_heart_rate_and_cadence(spec: RideSpec):
    """Average and max power, heart rate and cadence match the spec's segments.

    Given: each cycling fixture; segments hold constant power and cadence, HR follows power.
    Expect: the plain averages and maxima of the spec's per-second values; ``None`` for
    channels the ride didn't record.
    """
    frame = frame_for(spec.name)
    powers, heart_rates, cadences = spec.powers(), spec.heart_rates(), spec.cadences()

    if spec.has_power:
        assert basic.avg_power(frame) == pytest.approx(mean(powers))
        assert basic.max_power(frame) == max(powers)
    else:
        assert basic.avg_power(frame) is None, "no power meter means no average power"
    if spec.has_hr:
        assert basic.avg_hr(frame) == pytest.approx(mean(heart_rates))
        assert basic.max_hr(frame) == max(heart_rates)
    else:
        assert basic.avg_hr(frame) is None, "no strap means no average heart rate"
    assert basic.avg_cadence(frame) == pytest.approx(mean(cadences))


@pytest.mark.parametrize("spec", CYCLING, ids=lambda s: s.name)
def test_distance_and_speed(spec: RideSpec):
    """Distance comes from the device's odometer; average speed is distance over moving time.

    Given: each cycling fixture; speed is (P / 0.25)^(1/3) m/s each second.
    Expect: distance = the sum of every second's speed except the last (the odometer reads
    the distance *before* each second), within FIT's 1 cm resolution; max speed is the speed
    at max power.
    """
    frame = frame_for(spec.name)
    expected_distance = sum(speed_for_power(p) for p in spec.powers()[:-1])

    distance = basic.distance_m(frame)

    assert distance == pytest.approx(expected_distance, abs=0.05)
    assert basic.avg_speed_mps(frame) == pytest.approx(expected_distance / spec.duration_s)
    assert basic.max_speed_mps(frame) == pytest.approx(
        speed_for_power(max(spec.powers())), abs=1e-3
    )


@pytest.mark.parametrize("spec", CYCLING, ids=lambda s: s.name)
def test_ascent_ignores_less_than_a_metre_per_climb(spec: RideSpec):
    """Climbing is the sum of rises, less up to 1 m per climb (the noise threshold).

    Given: each cycling fixture; altitude is a sine wave per lap of the loop.
    Expect: between the exact total rise minus 1 m per climb (one climb per lap) and the
    exact total plus FIT's 0.2 m altitude resolution.
    """
    frame = frame_for(spec.name)
    altitudes = [s.altitude for s in samples(spec)]
    exact = sum(max(0.0, b - a) for a, b in pairwise(altitudes))
    climbs = math.ceil(samples(spec)[-1].distance / spec.loop.lap_length_m) + 1

    ascent = basic.ascent_m(frame)

    assert ascent is not None
    assert exact - climbs * 1.0 <= ascent <= exact + 0.2, (
        f"ascent {ascent:.1f} m should be just under the exact {exact:.1f} m"
    )


def test_location_summary_follows_the_loop():
    """Outdoor rides record where they started and the area they covered.

    Given: the outdoor interval ride on the 5 km loop near Roubaix (it starts on the loop's
    east side).
    Expect: start on the centre's latitude, one radius east of it; a bounding box one radius
    around the centre.
    """
    spec = ride("garmin_nord_intervals_5x4")
    radius = spec.loop.lap_length_m / (2 * math.pi)
    dlat = radius / METRES_PER_DEG_LAT
    dlon = radius / (METRES_PER_DEG_LAT * math.cos(math.radians(spec.loop.center_lat)))

    geo = basic.geo(frame_for(spec.name))

    assert geo is not None
    assert geo.start_lat == pytest.approx(spec.loop.center_lat, abs=1e-6)
    assert geo.start_lon == pytest.approx(spec.loop.center_lon + dlon, abs=1e-6)
    assert (geo.min_lat, geo.max_lat) == pytest.approx(
        (spec.loop.center_lat - dlat, spec.loop.center_lat + dlat), abs=1e-5
    ), "the box should span one radius north and south of the centre"
    assert basic.geo(frame_for("garmin_indoor_no_hr")) is None, "indoor rides have no location"


def test_laps_follow_the_lap_button():
    """Each lap's figures come from the samples between one lap press and the next.

    Given: the interval ride, which presses lap at every segment change (warm-up, 5 × work +
    rest, cool-down).
    Expect: 12 laps with each segment's start, length and power.
    """
    spec = ride("garmin_nord_intervals_5x4")
    frame = frame_for(spec.name)
    starts = [frame["timestamp"][0] + timedelta(seconds=sum(s.seconds for s in spec.segments[:i]))
              for i in range(len(spec.segments))]  # fmt: skip

    laps = basic.laps(frame, starts)

    assert [lap.elapsed_s for lap in laps] == [s.seconds for s in spec.segments]
    assert [lap.avg_power for lap in laps] == [s.power for s in spec.segments]
    assert [lap.start_offset_s for lap in laps] == [(start - starts[0]).seconds for start in starts]


def test_power_average_keeps_zeros_and_cadence_average_drops_them():
    """Coasting counts toward average power but not average cadence, as on Garmin and Zwift.

    Given: four seconds: 200 W at 90 rpm, two seconds coasting (0 W, 0 rpm), 200 W at 90 rpm.
    Expect: average power 100 W; average cadence 90 rpm.
    """
    frame = synthetic(
        [{"power": 200, "cadence": 90}, {"power": 0, "cadence": 0},
         {"power": 0, "cadence": 0}, {"power": 200, "cadence": 90}]
    )  # fmt: skip

    assert basic.avg_power(frame) == 100
    assert basic.avg_cadence(frame) == 90


def test_moving_time_without_speed_counts_pedalling_seconds():
    """With no speed sensor, moving time is the seconds spent pedalling or producing power.

    Given: five seconds with power and cadence but no speed, two of them at 0 W and 0 rpm.
    Expect: 3 seconds moving; no distance or speed.
    """
    frame = synthetic(
        [{"power": 150, "cadence": 80}, {"power": 0, "cadence": 0}, {"power": 160, "cadence": 82},
         {"power": 0, "cadence": 0}, {"power": 170, "cadence": 85}]
    )  # fmt: skip

    assert basic.moving_s(frame) == 3
    assert basic.distance_m(frame) is None, "no odometer or speed means no distance"
    assert basic.avg_speed_mps(frame) is None
