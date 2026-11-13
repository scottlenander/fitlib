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
