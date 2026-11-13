"""Canary: synthetic rides written with fit-tool decode unchanged with fitdecode on this Python.

This guards both FIT libraries on Python 3.14, since neither declares 3.14 support. It calls
fitdecode directly on purpose: it tests the library, not fitlib's own decoder.
"""

from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

import fitdecode
import pytest

from tests.fixtures.generate import build, samples
from tests.fixtures.specs import CORRUPT, RIDES, RideSpec, Source

SEMICIRCLE_TO_DEG = 180 / 2**31
METRES_PER_DEG_LAT = 111_320


def decode(path: Path) -> dict[str, list[dict]]:
    """All data messages in the file, grouped by message name."""
    messages: dict[str, list[dict]] = {}
    with fitdecode.FitReader(path) as reader:
        for frame in reader:
            if isinstance(frame, fitdecode.FitDataMessage):
                fields = {f.name: f.value for f in frame.fields}
                messages.setdefault(frame.name, []).append(fields)
    return messages


# Module scope: each ride is encoded and decoded once, then shared by the read-only tests below.
@pytest.fixture(scope="module", params=RIDES, ids=lambda spec: spec.name)
def ride(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[RideSpec, dict[str, list[dict]]]:
    spec: RideSpec = request.param
    path = tmp_path_factory.mktemp("roundtrip") / f"{spec.name}.fit"
    path.write_bytes(build(spec))
    return spec, decode(path)


def test_file_id_identifies_the_source(ride):
    """The file_id message says who recorded the ride.

    Given: each synthetic ride (Zwift, and Garmin Edge 540), encoded with fit-tool.
    Expect: an activity file whose manufacturer, Garmin product, serial number and creation time
    match the spec.
    """
    spec, messages = ride

    (file_id,) = messages["file_id"]

    assert file_id["type"] == "activity"
    if spec.source is Source.ZWIFT:
        assert file_id["manufacturer"] == "zwift"
    else:
        assert file_id["manufacturer"] == "garmin"
        assert file_id["garmin_product"] == "edge_540"
    assert file_id["serial_number"] == spec.serial_number
    assert file_id["time_created"] == spec.start, "creation time should be the ride's start"


def test_one_record_per_second(ride):
    """Records are sampled once per second for the whole ride.

    Given: each synthetic ride, whose spec sets a start time and a duration in seconds.
    Expect: one record per second, timestamped from the start time with no gaps or repeats.
    """
    spec, messages = ride

    records = messages["record"]
    timestamps = [r["timestamp"] for r in records]
    expected = [spec.start + timedelta(seconds=i) for i in range(spec.duration_s)]

    assert len(records) == spec.duration_s, "there should be one record per second of the ride"
    assert timestamps == expected, "timestamps should run 1 s apart from the ride's start"


def test_power_heart_rate_and_cadence_round_trip(ride):
    """Every second's power, heart rate and cadence decode to exactly what was written.

    Given: each synthetic ride, built from constant-power segments (HR derived from power).
    Expect: the decoded per-second values equal the spec's, in order.
    """
    spec, messages = ride

    records = messages["record"]
    powers = [r["power"] for r in records]
    heart_rates = [r["heart_rate"] for r in records]
    cadences = [r["cadence"] for r in records]

    assert powers == spec.powers(), "per-second power should match the spec"
    assert heart_rates == spec.heart_rates(), "per-second heart rate should match the spec"
    assert cadences == spec.cadences(), "per-second cadence should match the spec"


def test_positions_follow_the_loop(ride):
    """GPS positions decode to the generated track, which circles the loop's centre point.

    Given: each synthetic ride on its loop (near Roubaix for Garmin, Watopia for Zwift).
    Expect: every position within ~10 cm of the generated one, and on a circle whose radius
    matches the loop length.
    """
    spec, messages = ride
    radius_m = spec.loop.lap_length_m / (2 * math.pi)

    for second, (record, sample) in enumerate(zip(messages["record"], samples(spec), strict=True)):
        lat = record["position_lat"] * SEMICIRCLE_TO_DEG
        lon = record["position_long"] * SEMICIRCLE_TO_DEG
        north = (lat - spec.loop.center_lat) * METRES_PER_DEG_LAT
        east = (lon - spec.loop.center_lon) * METRES_PER_DEG_LAT * math.cos(math.radians(lat))

        # FIT stores positions as 32-bit semicircles: ~1 cm resolution.
        assert lat == pytest.approx(sample.lat, abs=1e-6), f"latitude at {second} s"
        assert lon == pytest.approx(sample.lon, abs=1e-6), f"longitude at {second} s"
        assert math.hypot(north, east) == pytest.approx(radius_m, rel=1e-3), (
            f"position at {second} s should be on the loop, {radius_m:.0f} m from its centre"
        )


def test_distance_speed_and_altitude_round_trip(ride):
    """Distance, speed and altitude decode to the generated values within FIT's precision.

    Given: each synthetic ride (speed derived from power, altitude a sine wave per lap).
    Expect: distance within 1 cm, speed within 1 mm/s, altitude within 0.2 m (FIT's 1/5 m
    resolution) for every second.
    """
    spec, messages = ride

    for second, (record, sample) in enumerate(zip(messages["record"], samples(spec), strict=True)):
        assert record["distance"] == pytest.approx(sample.distance, abs=0.01), (
            f"distance at {second} s"
        )
        assert record["speed"] == pytest.approx(sample.speed, abs=0.001), f"speed at {second} s"
        assert record["altitude"] == pytest.approx(sample.altitude, abs=0.2), (
            f"altitude at {second} s"
        )


def test_session_describes_the_ride(ride):
    """The session message summarises the ride the way Zwift or a Garmin would.

    Given: each synthetic ride.
    Expect: a cycling session, virtual for Zwift and road for Garmin, with the spec's start,
    duration, and average and max power.
    """
    spec, messages = ride
    expected_sub_sport = "virtual_activity" if spec.source is Source.ZWIFT else "road"
    expected_avg_power = round(sum(spec.powers()) / spec.duration_s)

    (session,) = messages["session"]

    assert session["sport"] == "cycling"
    assert session["sub_sport"] == expected_sub_sport, "Zwift rides should be virtual"
    assert session["start_time"] == spec.start
    assert session["total_elapsed_time"] == spec.duration_s
    assert session["avg_power"] == expected_avg_power
    assert session["max_power"] == max(spec.powers())


@pytest.mark.parametrize("name", CORRUPT)
def test_truncated_file_is_rejected(name: str, tmp_path: Path):
    """fitdecode refuses a file that was cut off part-way through.

    Given: a valid ride's bytes truncated to the length listed in ``CORRUPT``.
    Expect: decoding raises a ``fitdecode.FitError`` rather than returning partial data.
    """
    source_name, keep = CORRUPT[name]
    source = next(spec for spec in RIDES if spec.name == source_name)
    path = tmp_path / f"{name}.fit"
    path.write_bytes(build(source)[:keep])

    with pytest.raises(fitdecode.FitError):
        decode(path)
