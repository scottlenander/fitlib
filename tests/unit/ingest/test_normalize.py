"""Turning decoded records into a 1 Hz frame."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl

from fitlib.ingest.normalize import SCHEMA, to_frame

START = datetime(2025, 8, 2, 6, 30, tzinfo=UTC)


def record(second: float, power: int | None = 200, **fields) -> dict:
    """Build a decoded record at a number of seconds after 06:30 UTC.

    Args:
        second: Seconds after the start; fractions are allowed.
        power: Watts, or ``None``.
        **fields: Any other record fields, e.g. ``heart_rate=140``.

    Returns:
        The record as ``decode`` would produce it.
    """
    return {"timestamp": START + timedelta(seconds=second), "power": power, **fields}


def test_every_second_records_map_one_to_one():
    """A file recorded every second gives one active row per record.

    Given: records at 0, 1, 2 and 3 s.
    Expect: 4 rows with ``t`` 0-3, all active, values unchanged.
    """
    records = [record(s, power=200 + s) for s in range(4)]

    frame = to_frame(records)

    assert frame["t"].to_list() == [0, 1, 2, 3]
    assert frame["active"].all()
    assert frame["power"].to_list() == [200, 201, 202, 203]


def test_short_gaps_are_filled_with_the_previous_value():
    """Gaps of up to 5 s (Garmin smart recording) are filled as if recorded.

    Given: records at 0 s (200 W) and 5 s (250 W): a 5-second gap.
    Expect: 6 active rows; seconds 1-4 repeat 200 W.
    """
    records = [record(0, power=200), record(5, power=250)]

    frame = to_frame(records)

    assert frame.height == 6
    assert frame["active"].all(), "a 5-second gap is smart recording, not a pause"
    assert frame["power"].to_list() == [200, 200, 200, 200, 200, 250]


def test_long_gaps_are_pauses():
    """Longer gaps are pauses: rows exist for elapsed time but hold no values.

    Given: records at 0 s and 10 s (a 10-second gap).
    Expect: 11 rows; seconds 1-9 inactive with no power; the ends active.
    """
    records = [record(0), record(10)]

    frame = to_frame(records)

    assert frame.height == 11, "elapsed time should include the pause"
    assert frame["active"].to_list() == [True] + [False] * 9 + [True]
    assert frame["power"].null_count() == 9, "paused seconds should have no power"


def test_repeated_and_sub_second_timestamps():
    """Records are put on whole seconds; when two land on the same second the later one wins.

    Given: records at 0 s, 0.4 s (truncates to 0) and 1 s.
    Expect: 2 rows; second 0 holds the 0.4 s record's power.
    """
    records = [record(0, power=100), record(0.4, power=150), record(1, power=200)]

    frame = to_frame(records)

    assert frame["power"].to_list() == [150, 200]


def test_missing_channels_and_empty_input_keep_the_schema():
    """Columns always exist with the same types, even when a channel was never recorded.

    Given: records with power only, and no records at all.
    Expect: both frames have every schema column with its type; heart rate is all null.
    """
    only_power = to_frame([record(0), record(1)])
    empty = to_frame([])

    assert only_power.schema == pl.Schema(SCHEMA)
    assert empty.schema == pl.Schema(SCHEMA)
    assert empty.is_empty()
    assert only_power["heart_rate"].null_count() == 2, "unrecorded channels should be null"


# -- distance ---------------------------------------------------------------------------------


def test_distance_comes_from_the_odometer_when_every_record_has_it():
    """A device that records distance every second keeps its own odometer.

    Given: four records at 10 m/s whose odometer reads 100, 105, 120 and 140 m (not matching
        the speed, to tell the two apart).
    Expect: the odometer's values, untouched.
    """
    readings = [100.0, 105.0, 120.0, 140.0]
    records = [record(s, speed=10.0, distance=d) for s, d in enumerate(readings)]

    frame = to_frame(records)

    assert frame["distance"].to_list() == readings


def test_distance_is_rebuilt_from_speed_when_the_odometer_is_rare():
    """Zwift writes speed every second but the odometer on only a few records.

    Given: 10 records at 5 m/s then 10 at 8 m/s, with an odometer reading (0 m) on the
        first only, as Zwift writes.
    Expect: each second has the distance ridden before it: 0, 5, … 50 at the change, 122 at
        the last; not the lone 0 copied to every second.
    """
    records = [
        record(s, speed=5.0 if s < 10 else 8.0, **({"distance": 0.0} if s == 0 else {}))
        for s in range(20)
    ]

    frame = to_frame(records)

    distance = frame["distance"].to_list()
    assert distance[:3] == [0.0, 5.0, 10.0]
    assert distance[10] == 50.0
    assert distance[-1] == 50.0 + 9 * 8.0


def test_rebuilt_distance_starts_from_the_odometer_and_skips_pauses():
    """Rebuilt distance carries on from the first reading and doesn't grow while paused.

    Given: records at 10 m/s for 0-4 s (odometer 1000 m on the first) and 20-24 s, paused
        between.
    Expect: 1000-1040 m before the pause, nothing during it, 1050-1090 m after.
    """
    records = [
        record(s, speed=10.0, **({"distance": 1000.0} if s == 0 else {}))
        for s in [*range(5), *range(20, 25)]
    ]

    frame = to_frame(records)

    distance = frame["distance"].to_list()
    assert distance[:5] == [1000.0, 1010.0, 1020.0, 1030.0, 1040.0]
    assert distance[5:20] == [None] * 15, "paused seconds should have no distance"
    assert distance[20:] == [1050.0, 1060.0, 1070.0, 1080.0, 1090.0]


def test_a_rare_odometer_without_speed_is_left_as_it_is():
    """With no speed to add up, there's nothing better than the odometer's readings.

    Given: three records, an odometer reading on the first only, and no speed.
    Expect: the reading carried forward, as for any channel.
    """
    records = [record(0, distance=500.0), record(1), record(2)]

    frame = to_frame(records)

    assert frame["distance"].to_list() == [500.0, 500.0, 500.0]
