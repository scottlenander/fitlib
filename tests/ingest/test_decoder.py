"""Decoding .fit bytes into device, sport, local time, records and laps."""

from __future__ import annotations

import pytest

from fitlib.ingest.decoder import DecodeError, decode
from fitlib.ingest.source import detect_source, device_name, is_cycling, is_indoor
from fitlib.models import Source
from tests.fixtures.generate import FIT_DIR, committed_bytes, written_samples
from tests.fixtures.specs import RIDES, RideSpec


@pytest.mark.parametrize("spec", RIDES, ids=lambda s: s.name)
def test_decodes_every_fixture(spec: RideSpec):
    """Each synthetic ride decodes with its device, sport, local time, records and laps.

    Given: each ride spec's committed FIT file.
    Expect: manufacturer and sport as written, the local-time offset (Garmin only), one record
    per written sample with positions in degrees, and the spec's lap count.
    """
    decoded = decode(committed_bytes(spec.name))
    written = written_samples(spec)
    expected_laps = len(spec.segments) if spec.lap_per_segment else 1

    assert decoded.manufacturer == spec.source.value
    assert decoded.sport == spec.sport
    assert decoded.sub_sport == spec.sub_sport
    assert decoded.utc_offset_s == spec.utc_offset_s, "Garmin rides record local time (CEST)"
    assert len(decoded.records) == len(written), "one record per written sample"
    assert [r["power"] for r in decoded.records] == [s.power for s in written]
    assert len(decoded.laps) == expected_laps
    if spec.has_gps:
        first = decoded.records[0]
        assert first["lat"] == pytest.approx(written[0].lat, abs=1e-6), "degrees, not semicircles"
        assert first["lon"] == pytest.approx(written[0].lon, abs=1e-6), "degrees, not semicircles"


@pytest.mark.parametrize(
    "data",
    [(FIT_DIR / "corrupt_truncated.fit").read_bytes(), b"", b"not a fit file at all"],
    ids=["truncated", "empty", "text"],
)
def test_unreadable_data_raises_decode_error(data: bytes):
    """Anything that isn't a complete FIT file raises ``DecodeError``.

    Given: a truncated ride, empty bytes, and plain text.
    Expect: ``DecodeError`` (not a fitdecode exception or partial data).
    """
    with pytest.raises(DecodeError):
        decode(data)


def test_zwift_and_garmin_sources_and_devices():
    """Rides are attributed to Zwift or Garmin, with a readable device name.

    Given: the Zwift steady ride and the Garmin interval ride.
    Expect: Zwift/"Zwift" (its product id is a meaningless number) and Garmin/"Garmin Edge 540".
    """
    zwift = decode(committed_bytes("zwift_watopia_steady_60min"))
    garmin = decode(committed_bytes("garmin_nord_intervals_5x4"))

    assert (detect_source(zwift), device_name(zwift)) == (Source.ZWIFT, "Zwift")
    assert (detect_source(garmin), device_name(garmin)) == (Source.GARMIN, "Garmin Edge 540")


def test_runs_are_not_rides_and_indoor_is_detected():
    """Runs are recognised as not cycling; indoor rides by sub-sport or by having no GPS.

    Given: the run, the Zwift ride (virtual, has GPS), the Garmin indoor ride (no GPS) and an
    outdoor Garmin ride.
    Expect: only the run is not cycling; Zwift and the Garmin indoor ride are indoor.
    """
    run = decode(committed_bytes("garmin_nord_run_20min"))
    zwift = decode(committed_bytes("zwift_watopia_steady_60min"))
    indoor = decode(committed_bytes("garmin_indoor_no_hr"))
    outdoor = decode(committed_bytes("garmin_nord_pause_10min"))

    assert not is_cycling(run), "a run should not be imported as a ride"
    assert all(is_cycling(d) for d in (zwift, indoor, outdoor))
    assert is_indoor(zwift, has_gps=True), "Zwift is virtual even though it has coordinates"
    assert is_indoor(indoor, has_gps=False)
    assert not is_indoor(outdoor, has_gps=True)
