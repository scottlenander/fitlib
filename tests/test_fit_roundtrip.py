"""Canary: synthetic rides written with fit-tool decode unchanged with fitdecode on this Python.

This guards both FIT libraries on Python 3.14, since neither declares 3.14 support.
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
    spec, messages = ride
    (file_id,) = messages["file_id"]
    assert file_id["type"] == "activity"
    if spec.source is Source.ZWIFT:
        assert file_id["manufacturer"] == "zwift"
    else:
        assert file_id["manufacturer"] == "garmin"
        assert file_id["garmin_product"] == "edge_540"
    assert file_id["serial_number"] == spec.serial_number
    assert file_id["time_created"] == spec.start


def test_one_record_per_second(ride):
    spec, messages = ride
    records = messages["record"]
    assert len(records) == spec.duration_s
    expected = [spec.start + timedelta(seconds=i) for i in range(spec.duration_s)]
    assert [r["timestamp"] for r in records] == expected


def test_power_heart_rate_and_cadence_round_trip(ride):
    spec, messages = ride
    records = messages["record"]
    assert [r["power"] for r in records] == spec.powers()
    assert [r["heart_rate"] for r in records] == spec.heart_rates()
    assert [r["cadence"] for r in records] == spec.cadences()


def test_positions_follow_the_loop(ride):
    spec, messages = ride
    records = messages["record"]
    radius_m = spec.loop.lap_length_m / (2 * math.pi)
    for record, sample in zip(records, samples(spec), strict=True):
        lat = record["position_lat"] * SEMICIRCLE_TO_DEG
        lon = record["position_long"] * SEMICIRCLE_TO_DEG
        # FIT stores positions as 32-bit semicircles: ~1 cm resolution.
        assert lat == pytest.approx(sample.lat, abs=1e-6)
        assert lon == pytest.approx(sample.lon, abs=1e-6)
        north = (lat - spec.loop.center_lat) * 111_320
        east = (lon - spec.loop.center_lon) * 111_320 * math.cos(math.radians(lat))
        assert math.hypot(north, east) == pytest.approx(radius_m, rel=1e-3)


def test_distance_speed_and_altitude_round_trip(ride):
    spec, messages = ride
    for record, sample in zip(messages["record"], samples(spec), strict=True):
        assert record["distance"] == pytest.approx(sample.distance, abs=0.01)
        assert record["speed"] == pytest.approx(sample.speed, abs=0.001)
        assert record["altitude"] == pytest.approx(sample.altitude, abs=0.2)


def test_session_describes_the_ride(ride):
    spec, messages = ride
    (session,) = messages["session"]
    assert session["sport"] == "cycling"
    expected_sub_sport = "virtual_activity" if spec.source is Source.ZWIFT else "road"
    assert session["sub_sport"] == expected_sub_sport
    assert session["start_time"] == spec.start
    assert session["total_elapsed_time"] == spec.duration_s
    assert session["avg_power"] == round(sum(spec.powers()) / spec.duration_s)
    assert session["max_power"] == max(spec.powers())


@pytest.mark.parametrize("name", CORRUPT)
def test_truncated_file_is_rejected(name: str, tmp_path: Path):
    source_name, keep = CORRUPT[name]
    source = next(spec for spec in RIDES if spec.name == source_name)
    path = tmp_path / f"{name}.fit"
    path.write_bytes(build(source)[:keep])
    with pytest.raises(fitdecode.FitError):
        decode(path)
