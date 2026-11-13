"""Turn decoded records into a 1 Hz frame: one row per second from the first record to the last.

Devices don't always record every second. Garmin "smart recording" writes a record only when
something changes (gaps of a few seconds), and pausing the timer leaves a longer gap. Short
gaps (``MAX_FILL_GAP_S`` or less) are filled with the previous value, as if recorded; longer
gaps are pauses: their rows exist (so elapsed time is right) but hold no values and are marked
``active = False``.
"""

from __future__ import annotations

from typing import Any

import polars as pl

MAX_FILL_GAP_S = 5

SCHEMA: dict[str, pl.DataType] = {
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
VALUE_COLUMNS = [c for c in SCHEMA if c not in ("t", "timestamp", "active")]


def empty_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=SCHEMA)


def to_frame(records: list[dict[str, Any]]) -> pl.DataFrame:
    if not records:
        return empty_frame()

    raw = pl.DataFrame(
        [{c: r.get(c) for c in ("timestamp", *VALUE_COLUMNS)} for r in records],
        schema={c: SCHEMA[c] for c in ("timestamp", *VALUE_COLUMNS)},
        orient="row",
    )
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
    return frame.select(list(SCHEMA)).cast(SCHEMA)
