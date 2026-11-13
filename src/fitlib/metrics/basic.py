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
    return frame.filter(pl.col("active"))


def has_data(frame: pl.DataFrame, column: str) -> bool:
    return frame[column].drop_nulls().len() > 0


def elapsed_s(frame: pl.DataFrame) -> int:
    """Start to finish, pauses included."""
    return frame.height


def moving_s(frame: pl.DataFrame) -> int:
    """Seconds actually riding: not paused, and moving (or pedalling, when there's no speed)."""
    active = _active(frame)
    if has_data(active, "speed"):
        return active.filter(pl.col("speed") >= MOVING_SPEED_MPS).height
    if has_data(active, "cadence") or has_data(active, "power"):
        pedalling = (pl.col("cadence").fill_null(0) > 0) | (pl.col("power").fill_null(0) > 0)
        return active.filter(pedalling).height
    return active.height


def distance_m(frame: pl.DataFrame) -> float | None:
    """From the device's cumulative distance; otherwise integrated from speed."""
    if has_data(frame, "distance"):
        distance = frame["distance"].drop_nulls()
        return float(distance.max() - distance.min())
    active = _active(frame)
    if has_data(active, "speed"):
        return float(active["speed"].fill_null(0).sum())
    return None


def ascent_m(frame: pl.DataFrame) -> float | None:
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
    values = series.drop_nulls()
    return float(values.mean()) if values.len() else None  # type: ignore[arg-type]


def _max(series: pl.Series) -> float | None:
    values = series.drop_nulls()
    return values.max() if values.len() else None  # type: ignore[return-value]


def avg_speed_mps(frame: pl.DataFrame) -> float | None:
    distance, moving = distance_m(frame), moving_s(frame)
    return distance / moving if distance is not None and moving else None


def max_speed_mps(frame: pl.DataFrame) -> float | None:
    value = _max(frame["speed"])
    return float(value) if value is not None else None


def avg_power(frame: pl.DataFrame) -> float | None:
    """Over every riding second, zeros included (coasting counts), as Garmin and Zwift do."""
    return _mean(_active(frame)["power"])


def max_power(frame: pl.DataFrame) -> int | None:
    value = _max(frame["power"])
    return int(value) if value is not None else None


def avg_hr(frame: pl.DataFrame) -> float | None:
    return _mean(_active(frame)["heart_rate"])


def max_hr(frame: pl.DataFrame) -> int | None:
    value = _max(frame["heart_rate"])
    return int(value) if value is not None else None


def avg_cadence(frame: pl.DataFrame) -> float | None:
    """While pedalling: zeros (coasting) are left out, as Garmin and Zwift do."""
    cadence = _active(frame)["cadence"]
    return _mean(cadence.filter(cadence > 0))


def geo(frame: pl.DataFrame) -> GeoSummary | None:
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
    """Each lap's figures, computed from the frame between one lap start and the next."""
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
