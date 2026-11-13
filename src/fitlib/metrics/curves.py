"""Best efforts: the highest average a channel held over each of a set of durations."""

from __future__ import annotations

import polars as pl

from fitlib.models import CURVE_DURATIONS_S, Curve


def best_averages(frame: pl.DataFrame, column: str) -> Curve:
    """Find the best average of a channel over each curve duration.

    Windows are taken over the 1 Hz grid, so a window that crosses a pause (or any second
    with no value) doesn't count: every best effort is continuous riding.

    Args:
        frame: The ride's 1 Hz frame.
        column: The channel, e.g. ``"power"`` or ``"heart_rate"``.

    Returns:
        ``(duration, best average)`` for each duration in ``CURVE_DURATIONS_S`` that has at
        least one complete window; empty if the channel wasn't recorded.
    """
    values = frame[column].cast(pl.Float64)
    if values.drop_nulls().is_empty():
        return ()
    points = []
    for duration in CURVE_DURATIONS_S:
        if duration > values.len():
            break
        best = values.rolling_mean(window_size=duration, min_samples=duration).max()
        if best is not None:
            points.append((duration, float(best)))  # type: ignore[arg-type]
    return tuple(points)


def best_at(curve: Curve, duration_s: int) -> float | None:
    """Look up one duration on a curve.

    Args:
        curve: A curve from ``best_averages``.
        duration_s: One of ``CURVE_DURATIONS_S``.

    Returns:
        The best average for that duration, or ``None`` if the ride had no such effort.
    """
    return next((value for d, value in curve if d == duration_s), None)
