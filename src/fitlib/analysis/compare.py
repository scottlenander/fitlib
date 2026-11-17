"""Lining rides up against each other, for overlaid charts.

Rides are put on one shared x axis: seconds from the start, or metres ridden. Lining up by
distance is what makes rides of the same route comparable: the same point on the road sits at
the same x, however long each ride took to get there, and the difference in when each ride got
there is the time gap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import polars as pl

# The fewest and most rides compared at once.
MIN_RIDES = 2
MAX_RIDES = 4
# The channels overlaid, and those smoothed when smoothing is on (the noisy ones).
FIELDS = ("power", "heart_rate", "cadence", "speed", "altitude")
SMOOTHED = ("power", "heart_rate")
# Smoothing choices, in seconds (0 is off).
SMOOTHING_S = (0, 10, 30)
# Points along the x axis: about one per pixel on a wide screen.
DEFAULT_POINTS = 1500

type Align = Literal["time", "distance"]
type Values = list[float | None]


class NoDistance(ValueError):
    """A ride can't be lined up by distance because it recorded none.

    Attributes:
        index: Which of the rides (from 0) has no distance.
    """

    def __init__(self, index: int) -> None:
        """Name the ride without distance.

        Args:
            index: Its position among the rides compared.
        """
        super().__init__(f"Ride {index + 1} recorded no distance, so it can't be lined up by it")
        self.index = index


@dataclass(frozen=True)
class Aligned:
    """Rides on one shared x axis.

    Attributes:
        align: ``time`` (x in seconds from the start) or ``distance`` (x in metres).
        x: The shared axis.
        series: For each ride, in order, each channel it recorded, with one value per ``x``
            (``None`` where it has none, such as past its end or during a pause).
        gap: With ``distance`` only: for each ride, the seconds it took to reach each ``x``
            minus the first ride's. Positive means behind the first ride.
    """

    align: Align
    x: list[float]
    series: list[dict[str, Values]]
    gap: list[Values] | None


def has_distance(frame: pl.DataFrame) -> bool:
    """Whether a ride recorded distance, so it can be lined up by it.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        True when it has distance beyond the start.
    """
    distance = frame["distance"].drop_nulls()
    return not distance.is_empty() and (distance.max() or 0) > 0  # type: ignore[operator]


def smooth(frame: pl.DataFrame, seconds: int) -> pl.DataFrame:
    """Smooth the noisy channels with a centred rolling average.

    Seconds with no value (pauses, dropouts) stay empty, so smoothing never fills a gap.

    Args:
        frame: The ride's 1 Hz frame.
        seconds: The window; 0 or 1 leaves the frame as it is.

    Returns:
        The frame with ``SMOOTHED`` channels averaged as floats.
    """
    if seconds <= 1:
        return frame
    return frame.with_columns(
        pl.when(pl.col(c).is_null())
        .then(None)
        .otherwise(pl.col(c).cast(pl.Float64).rolling_mean(seconds, min_samples=1, center=True))
        .alias(c)
        for c in SMOOTHED
    )


def _recorded(frames: list[pl.DataFrame]) -> list[list[str]]:
    """The channels each ride recorded.

    Args:
        frames: The rides' frames.

    Returns:
        For each ride, the ``FIELDS`` it has any value for.
    """
    return [[f for f in FIELDS if frame[f].null_count() < frame.height] for frame in frames]


def _values(series: pl.Series) -> Values:
    """Round a channel for sending: whole numbers stay whole, others keep 2 decimals.

    Args:
        series: The channel.

    Returns:
        Its values, ``None`` where empty.
    """
    if series.dtype.is_integer():
        return series.to_list()
    return [None if v is None or math.isnan(v) else round(v, 2) for v in series.to_list()]


def align_time(frames: list[pl.DataFrame], points: int = DEFAULT_POINTS) -> Aligned:
    """Line rides up by time from their start.

    The axis runs to the end of the longest ride, every ``step`` seconds, with ``step``
    chosen to give at most about ``points`` points. Shorter rides end early.

    Args:
        frames: The rides' 1 Hz frames, smoothed if wanted.
        points: Roughly how many points to return.

    Returns:
        The rides on a shared time axis, without a time gap.
    """
    longest = max(frame.height for frame in frames)
    step = max(1, math.ceil(longest / points))
    x = list(range(0, longest, step))
    series = []
    for frame, fields in zip(frames, _recorded(frames), strict=True):
        sampled = frame.gather_every(step)
        padding = [None] * (len(x) - sampled.height)
        series.append({f: _values(sampled[f]) + padding for f in fields})
    return Aligned(align="time", x=[float(v) for v in x], series=series, gap=None)


def _time_at(frame: pl.DataFrame, at: pl.Series, grid: pl.Series) -> list[float]:
    """Work out when a ride reached each distance, between whole seconds.

    Samples are a second apart, so the second a distance was first reached can be up to a
    second late. Interpolating from the second before keeps the time gap smooth.

    Args:
        frame: The ride's samples with distance, in order.
        at: For each grid distance, the first sample at or past it.
        grid: The distances.

    Returns:
        Seconds from the start for each grid distance.
    """
    before = (at - 1).clip(0, frame.height - 1)
    d0, d1 = frame["distance"].gather(before), frame["distance"].gather(at)
    t0, t1 = frame["t"].gather(before).cast(pl.Float64), frame["t"].gather(at).cast(pl.Float64)
    share = ((grid - d0) / (d1 - d0)).fill_nan(1.0).clip(0.0, 1.0)
    return (t0 + (t1 - t0) * share).to_list()


def align_distance(frames: list[pl.DataFrame], points: int = DEFAULT_POINTS) -> Aligned:
    """Line rides up by distance ridden.

    The axis runs from 0 to the end of the shortest ride, so every ride covers all of it.
    At each point, each ride's values are those of the first second it had ridden that far,
    and its time is when it got there (elapsed, so stops and pauses count, as on a bike
    computer), between whole seconds.

    Args:
        frames: The rides' 1 Hz frames, smoothed if wanted.
        points: How many points to return.

    Returns:
        The rides on a shared distance axis, with each ride's time gap to the first.

    Raises:
        NoDistance: A ride recorded no distance.
    """
    riding = []
    for index, frame in enumerate(frames):
        if not has_distance(frame):
            raise NoDistance(index)
        # Distance only grows; cum_max guards against a device stepping it back.
        riding.append(
            frame.filter(pl.col("distance").is_not_null()).with_columns(
                pl.col("distance").cum_max()
            )
        )
    end = min(frame["distance"][-1] for frame in riding)
    count = max(2, points)
    x = [end * i / (count - 1) for i in range(count)]
    grid = pl.Series(x, dtype=pl.Float64)
    series = []
    times: list[list[float]] = []
    for frame, fields in zip(riding, _recorded(frames), strict=True):
        at = frame["distance"].search_sorted(grid, side="left").clip(0, frame.height - 1)
        reached = frame.select(pl.all().gather(at))
        series.append({f: _values(reached[f]) for f in fields})
        times.append(_time_at(frame, at, grid))
    gap: list[Values] = [
        [round(t - first, 1) for t, first in zip(ride, times[0], strict=True)] for ride in times
    ]
    return Aligned(align="distance", x=[round(v, 1) for v in x], series=series, gap=gap)


def align(
    frames: list[pl.DataFrame],
    by: Align,
    smoothing_s: int = 0,
    points: int = DEFAULT_POINTS,
) -> Aligned:
    """Smooth rides, then line them up.

    Args:
        frames: The rides' 1 Hz frames, the first being the one others are measured against.
        by: ``time`` or ``distance``.
        smoothing_s: Rolling-average window for power and heart rate; 0 for none.
        points: Roughly how many points to return.

    Returns:
        The rides on a shared axis.

    Raises:
        NoDistance: Lining up by distance, and a ride recorded no distance.
    """
    smoothed = [smooth(frame, smoothing_s) for frame in frames]
    if by == "distance":
        return align_distance(smoothed, points)
    return align_time(smoothed, points)
