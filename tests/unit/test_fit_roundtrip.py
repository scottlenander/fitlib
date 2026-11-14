"""Canary: synthetic rides written with fit-tool decode unchanged with fitdecode on this Python.

This guards both FIT libraries on Python 3.14, since neither declares 3.14 support. It calls
fitdecode directly on purpose: it tests the library, not fitlib's own decoder.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import fitdecode
import pytest

from tests.fixtures.generate import build, written_samples
from tests.fixtures.specs import CORRUPT, RIDES, RideSpec, Source

SEMICIRCLE_TO_DEG = 180 / 2**31
METRES_PER_DEG_LAT = 111_320


def decode(path: Path) -> dict[str, list[dict]]:
    """Read a FIT file directly with fitdecode.

    Args:
        path: The file.

    Returns:
        The fields of every data message, grouped by message name.
    """
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
    """Encode each ride spec and decode it again, once per module.

    Args:
        request: Pytest request; its param is the ride spec.
        tmp_path_factory: Makes the folder the file is written to.

    Returns:
        The spec and its decoded messages.
    """
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


def test_record_timestamps_match_what_was_written(ride):
    """Each record keeps its timestamp, including across pauses and smart-recording gaps.

    Given: each synthetic ride, recorded every second or at irregular 1-5 s intervals, some
    with a timer pause.
    Expect: one record per written sample, with the same wall-clock timestamps in order.
    """
    spec, messages = ride
    written = written_samples(spec)

    timestamps = [r["timestamp"] for r in messages["record"]]
    expected = [datetime.fromtimestamp(s.timestamp_ms / 1000, UTC) for s in written]

    assert len(timestamps) == len(written), "there should be one record per written sample"
    assert timestamps == expected, "record timestamps should match the written samples"


def test_power_heart_rate_and_cadence_round_trip(ride):
    """Each record's power, heart rate and cadence decode to exactly what was written.

    Given: each synthetic ride, built from constant-power segments (HR derived from power);
    rides without a power meter or HR strap leave those fields out.
    Expect: the decoded values equal the written ones in order, and absent channels decode as
    missing rather than zero.
    """
    spec, messages = ride
    written = written_samples(spec)

    records = messages["record"]
    powers = [r.get("power") for r in records]
    heart_rates = [r.get("heart_rate") for r in records]
    cadences = [r["cadence"] for r in records]

    assert powers == [s.power for s in written], "power should match (None without a meter)"
    assert heart_rates == [s.heart_rate for s in written], (
        "heart rate should match (None without a strap)"
    )
    assert cadences == [s.cadence for s in written], "cadence should match the spec"


def test_positions_follow_the_loop(ride):
    """GPS positions decode to the generated track, which circles the loop's centre point.

    Given: each synthetic ride; outdoor and Zwift rides follow their loop (near Roubaix, or
    Watopia), indoor Garmin rides have no GPS.
    Expect: every position within ~10 cm of the generated one and on a circle whose radius
    matches the loop length; indoor rides have no positions at all.
    """
    spec, messages = ride
    records = messages["record"]
    radius_m = spec.loop.lap_length_m / (2 * math.pi)

    if not spec.has_gps:
        assert all("position_lat" not in r for r in records), "indoor rides should have no GPS"
        return

    for record, sample in zip(records, written_samples(spec), strict=True):
        second = sample.second
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
    resolution) for every record.
    """
    spec, messages = ride

    for record, sample in zip(messages["record"], written_samples(spec), strict=True):
        second = sample.second
        assert record["distance"] == pytest.approx(sample.distance, abs=0.01), (
            f"distance at {second} s"
        )
        assert record["speed"] == pytest.approx(sample.speed, abs=0.001), f"speed at {second} s"
        assert record["altitude"] == pytest.approx(sample.altitude, abs=0.2), (
            f"altitude at {second} s"
        )


def test_session_describes_the_ride(ride):
    """The session message summarises the ride the way Zwift or a Garmin would.

    Given: each synthetic ride, including a run, an indoor ride and a ride with a pause.
    Expect: the spec's sport and sub-sport, start, elapsed time (pauses included), timer time
    (pauses excluded), and average and max power when there is a power meter.
    """
    spec, messages = ride

    (session,) = messages["session"]

    assert session["sport"] == spec.sport
    assert session["sub_sport"] == spec.sub_sport, "Zwift virtual, Garmin road or indoor"
    assert session["start_time"] == spec.start
    assert session["total_elapsed_time"] == spec.elapsed_s, "elapsed time includes pauses"
    assert session["total_timer_time"] == spec.duration_s, "timer time excludes pauses"
    if spec.has_power:
        assert session["avg_power"] == round(sum(spec.powers()) / spec.duration_s)
        assert session["max_power"] == max(spec.powers())
    else:
        assert "avg_power" not in session, "rides without a power meter have no average power"


def test_laps_match_the_spec(ride):
    """Rides recorded with the lap button have one lap per segment; others have one lap.

    Given: each synthetic ride; the interval ride presses lap at every segment change.
    Expect: as many lap messages as the spec's segments (lap button) or exactly one.
    """
    spec, messages = ride
    expected = len(spec.segments) if spec.lap_per_segment else 1

    laps = messages["lap"]

    assert len(laps) == expected, "lap count should follow the spec's lap setting"


@pytest.mark.parametrize("name", CORRUPT)
def test_truncated_file_is_rejected(name: str, tmp_path: Path):
    """A file cut off part-way through is refused by fitdecode.

    Given: a valid ride's bytes truncated to the length listed in ``CORRUPT``.
    Expect: decoding raises a ``fitdecode.FitError`` rather than returning partial data.
    """
    source_name, keep = CORRUPT[name]
    source = next(spec for spec in RIDES if spec.name == source_name)
    path = tmp_path / f"{name}.fit"
    path.write_bytes(build(source)[:keep])

    with pytest.raises(fitdecode.FitError):
        decode(path)
