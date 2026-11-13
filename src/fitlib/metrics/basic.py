"""Time, distance, climbing, speed, and simple power / heart-rate / cadence figures.

All functions take the 1 Hz frame from ``fitlib.ingest.normalize`` and ignore paused rows
(``active = False``).
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from fitlib.models import GeoSummary, Lap

# Below this speed the rider is treated as stopped (1.8 km/h).
MOVING_SPEED_MPS = 0.5
# Climbing is counted once the road has risen this much since the last low point, which
# ignores altimeter noise.
ASCENT_THRESHOLD_M = 1.0


def _active(frame: pl.DataFrame) -> pl.DataFrame:
    """Keep only the seconds when the timer was running.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        The rows with ``active`` true.
    """
    return frame.filter(pl.col("active"))


def has_data(frame: pl.DataFrame, column: str) -> bool:
    """Check whether a channel was recorded at all.

    Args:
        frame: The ride's 1 Hz frame.
        column: A column name, e.g. ``"power"``.

    Returns:
        ``True`` if the column has at least one value.
    """
    return frame[column].drop_nulls().len() > 0


def elapsed_s(frame: pl.DataFrame) -> int:
    """Time from start to finish, pauses included.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Elapsed seconds (one per row).
    """
    return frame.height


def moving_s(frame: pl.DataFrame) -> int:
    """Time spent actually riding.

    A second counts when the timer was running and the bike was moving (at least
    ``MOVING_SPEED_MPS``). Without a speed sensor, seconds with pedalling or power count
    instead; with neither, every running second counts.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Moving seconds.
    """
    active = _active(frame)
    if has_data(active, "speed"):
        return active.filter(pl.col("speed") >= MOVING_SPEED_MPS).height
    if has_data(active, "cadence") or has_data(active, "power"):
        pedalling = (pl.col("cadence").fill_null(0) > 0) | (pl.col("power").fill_null(0) > 0)
        return active.filter(pedalling).height
    return active.height


def distance_m(frame: pl.DataFrame) -> float | None:
    """Distance covered.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Metres, from the device's odometer if recorded, otherwise the sum of each running
        second's speed; ``None`` with neither.
    """
    if has_data(frame, "distance"):
        distance = frame["distance"].drop_nulls()
        return float(distance.max() - distance.min())
    active = _active(frame)
    if has_data(active, "speed"):
        return float(active["speed"].fill_null(0).sum())
    return None


def ascent_m(frame: pl.DataFrame) -> float | None:
    """Total climbing, ignoring altimeter noise.

    A climb is counted once the altitude has risen ``ASCENT_THRESHOLD_M`` above the last low
    point, so wobbles smaller than that add nothing.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Metres climbed, or ``None`` without altitude data.
    """
    altitude = frame["altitude"].drop_nulls().to_list()
    if not altitude:
        return None
    total, low = 0.0, altitude[0]
    for value in altitude[1:]:
        if value < low:
            low = value
        elif value - low >= ASCENT_THRESHOLD_M:
            total += value - low
            low = value
    return total


def _mean(series: pl.Series) -> float | None:
    """Average of the values present.

    Args:
        series: Any numeric column.

    Returns:
        The mean ignoring nulls, or ``None`` if there are no values.
    """
    values = series.drop_nulls()
    return float(values.mean()) if values.len() else None  # type: ignore[arg-type]


def _max(series: pl.Series) -> float | None:
    """Largest of the values present.

    Args:
        series: Any numeric column.

    Returns:
        The maximum ignoring nulls, or ``None`` if there are no values.
    """
    values = series.drop_nulls()
    return values.max() if values.len() else None  # type: ignore[return-value]


def avg_speed_mps(frame: pl.DataFrame) -> float | None:
    """Average moving speed.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Distance divided by moving time, in m/s; ``None`` without distance or moving time.
    """
    distance, moving = distance_m(frame), moving_s(frame)
    return distance / moving if distance is not None and moving else None


def max_speed_mps(frame: pl.DataFrame) -> float | None:
    """Highest speed.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Metres per second, or ``None`` without speed data.
    """
    value = _max(frame["speed"])
    return float(value) if value is not None else None


def avg_power(frame: pl.DataFrame) -> float | None:
    """Average power over the running seconds, zeros included, as Garmin and Zwift do.

    Coasting counts toward the average.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Watts, or ``None`` without a power meter.
    """
    return _mean(_active(frame)["power"])


def max_power(frame: pl.DataFrame) -> int | None:
    """Highest power.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Watts, or ``None`` without a power meter.
    """
    value = _max(frame["power"])
    return int(value) if value is not None else None


def avg_hr(frame: pl.DataFrame) -> float | None:
    """Average heart rate over the running seconds.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Beats per minute, or ``None`` without a heart-rate strap.
    """
    return _mean(_active(frame)["heart_rate"])


def max_hr(frame: pl.DataFrame) -> int | None:
    """Highest heart rate.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Beats per minute, or ``None`` without a heart-rate strap.
    """
    value = _max(frame["heart_rate"])
    return int(value) if value is not None else None


def avg_cadence(frame: pl.DataFrame) -> float | None:
    """Average cadence while pedalling, as Garmin and Zwift do.

    Zeros (coasting) are left out.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Revolutions per minute, or ``None`` without cadence data.
    """
    cadence = _active(frame)["cadence"]
    return _mean(cadence.filter(cadence > 0))


def geo(frame: pl.DataFrame) -> GeoSummary | None:
    """Where the ride started and the area it covered.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        The first position and the bounding box of all positions, or ``None`` without GPS.
    """
    points = frame.select("lat", "lon").drop_nulls()
    if points.is_empty():
        return None
    return GeoSummary(
        start_lat=float(points["lat"][0]),
        start_lon=float(points["lon"][0]),
        min_lat=float(points["lat"].min()),  # type: ignore[arg-type]
        min_lon=float(points["lon"].min()),  # type: ignore[arg-type]
        max_lat=float(points["lat"].max()),  # type: ignore[arg-type]
        max_lon=float(points["lon"].max()),  # type: ignore[arg-type]
    )


def laps(frame: pl.DataFrame, lap_starts: list[datetime]) -> tuple[Lap, ...]:
    """Compute each lap's figures from the samples between one lap start and the next.

    Args:
        frame: The ride's 1 Hz frame.
        lap_starts: When each lap started, in UTC, from the file's lap messages. Starts
            before the first sample count as the ride's start; duplicates are merged.

    Returns:
        One ``Lap`` per non-empty lap, in order; empty if there are no samples or laps.
    """
    if frame.is_empty() or not lap_starts:
        return ()
    start: datetime = frame["timestamp"][0]
    offsets = sorted({max(0, int((lap - start).total_seconds())) for lap in lap_starts})
    bounds = [*offsets, frame.height]
    result = []
    for index, (lo, hi) in enumerate(zip(bounds, bounds[1:], strict=False)):
        part = frame.slice(lo, hi - lo)
        if part.is_empty():
            continue
        result.append(
            Lap(
                index=index,
                start_offset_s=lo,
                elapsed_s=part.height,
                distance_m=distance_m(part),
                avg_power=avg_power(part),
                max_power=max_power(part),
                avg_hr=avg_hr(part),
                max_hr=max_hr(part),
            )
        )
    return tuple(result)
