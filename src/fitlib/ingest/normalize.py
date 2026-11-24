"""Turn decoded records into a 1 Hz frame: one row per second from the first record to the last.

Distance comes from the device's odometer when most records carry it. Otherwise (Zwift writes
it on only a few records) it is rebuilt by adding up each running second's speed, so every
second still has the distance ridden before it.

Devices don't always record every second. Garmin "smart recording" writes a record only when
something changes (gaps of a few seconds), and pausing the timer leaves a longer gap. Short
gaps (``MAX_FILL_GAP_S`` or less) are filled with the previous value, as if recorded; longer
gaps are pauses: their rows exist (so elapsed time is right) but hold no values and are marked
``active = False``.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from fitlib.metrics.scalars import as_float

MAX_FILL_GAP_S = 5
# The device's odometer is used when at least this share of records carry it; otherwise
# distance is worked out from speed. Zwift writes speed every second but the odometer on
# only a few records.
MIN_ODOMETER_SHARE = 0.9

SCHEMA = pl.Schema(
    {
        "t": pl.Int32(),  # seconds since the first record
        "timestamp": pl.Datetime("us", "UTC"),
        "active": pl.Boolean(),  # recorded, or inside a short gap; False during pauses
        "power": pl.Int32(),
        "heart_rate": pl.Int32(),
        "cadence": pl.Int32(),
        "speed": pl.Float64(),  # m/s
        "distance": pl.Float64(),  # m, cumulative
        "altitude": pl.Float64(),  # m
        "lat": pl.Float64(),  # degrees
        "lon": pl.Float64(),  # degrees
        "temperature": pl.Int32(),  # °C
    }
)
VALUE_COLUMNS = [c for c in SCHEMA if c not in ("t", "timestamp", "active")]


def empty_frame() -> pl.DataFrame:
    """A frame with no rows but every column of ``SCHEMA``.

    Returns:
        The empty frame.
    """
    return pl.DataFrame(schema=SCHEMA)


def to_frame(records: list[dict[str, Any]]) -> pl.DataFrame:
    """Put decoded records on a 1-second grid from the first record to the last.

    Timestamps are truncated to whole seconds; when two records land on the same second the
    later one wins. Gaps up to ``MAX_FILL_GAP_S`` are filled with the previous values; longer
    gaps become paused rows (``active`` false, values null). Distance is rebuilt from speed
    when the odometer is on fewer than ``MIN_ODOMETER_SHARE`` of records.

    Args:
        records: Decoded records (see ``DecodedActivity.records``), in any order.

    Returns:
        A frame with the columns and types of ``SCHEMA``; empty if there are no records.
    """
    if not records:
        return empty_frame()

    raw = pl.DataFrame(
        [{c: r.get(c) for c in ("timestamp", *VALUE_COLUMNS)} for r in records],
        schema={c: SCHEMA[c] for c in ("timestamp", *VALUE_COLUMNS)},
        orient="row",
    )
    # Measured before gaps are filled, which would copy a lone reading onto every second.
    odometer_share = as_float(raw["distance"].is_not_null().mean() or 0.0)
    raw = (
        raw.with_columns(pl.col("timestamp").dt.truncate("1s"))
        .unique("timestamp", keep="last", maintain_order=True)
        .sort("timestamp")
        .with_columns(
            gap_after=(pl.col("timestamp").shift(-1) - pl.col("timestamp"))
            .dt.total_seconds()
            .fill_null(1),
            recorded=pl.lit(True),
        )
    )

    grid = raw.upsample("timestamp", every="1s").with_columns(
        pl.col("gap_after").forward_fill(),
        pl.col("recorded").fill_null(False),
    )
    active = pl.col("recorded") | (pl.col("gap_after") <= MAX_FILL_GAP_S)
    frame = grid.with_columns(
        [
            pl.when(active).then(pl.col(c).forward_fill()).otherwise(None).alias(c)
            for c in VALUE_COLUMNS
        ]
    ).with_columns(
        active=active,
        t=pl.int_range(pl.len(), dtype=pl.Int32),
    )
    if odometer_share < MIN_ODOMETER_SHARE:
        frame = _distance_from_speed(frame)
    return frame.select(list(SCHEMA)).cast(SCHEMA)


def _distance_from_speed(frame: pl.DataFrame) -> pl.DataFrame:
    """Rebuild distance by adding up each running second's speed.

    Like an odometer, each second gets the distance ridden *before* it, starting from the
    first odometer reading (or 0). Paused seconds stay empty. Without any speed, the frame
    is left as it is.

    Args:
        frame: The 1 Hz frame, with ``active`` and ``speed``.

    Returns:
        The frame with ``distance`` replaced.
    """
    if frame["speed"].null_count() == frame.height:
        return frame
    first = frame["distance"].drop_nulls()
    start = float(first[0]) if not first.is_empty() else 0.0
    ridden = pl.when(pl.col("active")).then(pl.col("speed").fill_null(0.0)).otherwise(0.0)
    return frame.with_columns(
        distance=pl.when(pl.col("active"))
        .then(start + ridden.cum_sum().shift(1, fill_value=0.0))
        .otherwise(None)
    )
