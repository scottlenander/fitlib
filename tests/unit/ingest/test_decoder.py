"""Decoding .fit bytes into device, sport, local time, records and laps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fitlib.ingest.decoder import FIT_EPOCH, DecodeError, _utc_offset, decode
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
    assert decoded.utc_offset_s == spec.utc_offset_s, (
        "Garmin rides record local time (CEST); Zwift's 1989 local time is ignored"
    )
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


END = datetime(2025, 8, 2, 7, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("local", "expected"),
    [
        (END + timedelta(hours=2), 2 * 3600),
        (int((END - FIT_EPOCH).total_seconds()) + 2 * 3600, 2 * 3600),
        (END - timedelta(hours=5, seconds=3), -5 * 3600),
        (END + timedelta(hours=5, minutes=45), 5 * 3600 + 45 * 60),
        (END + timedelta(hours=14), 14 * 3600),
        (END - timedelta(hours=12), -12 * 3600),
        (FIT_EPOCH, None),
        (0, None),
        (3600, None),
        (END + timedelta(hours=15), None),
        (END - timedelta(days=1), None),
        (None, None),
    ],
    ids=[
        "cest",
        "cest-as-seconds",
        "us-eastern-with-clock-drift",
        "nepal",
        "kiribati",
        "baker-island",
        "zwift-fit-epoch",
        "zero-seconds",
        "relative-seconds",
        "beyond-plus-14h",
        "a-day-off",
        "missing",
    ],
)
def test_utc_offset_only_from_real_local_times(local, expected):
    """The time zone comes from the local time only when it is a real one.

    Given: an activity ending 07:30 UTC with local times as dates or seconds since the FIT
        epoch: real zones (to the nearest 15 minutes), the FIT epoch Zwift writes, seconds
        since power-on, and offsets no time zone has.
    Expect: the offset for real zones, otherwise no local time.
    """
    offset = _utc_offset({"timestamp": END, "local_timestamp": local})

    assert offset == expected


def test_zwift_ride_with_fit_epoch_local_time_has_no_offset():
    """Zwift's local time of 1989-12-31 is ignored, so the ride keeps its real date.

    Given: the Zwift fixture, which writes the FIT epoch as its local time, as Zwift does.
    Expect: no UTC offset (dates fall back to UTC), not one of about -35 years.
    """
    decoded = decode(committed_bytes("zwift_watopia_steady_60min"))

    assert decoded.utc_offset_s is None
