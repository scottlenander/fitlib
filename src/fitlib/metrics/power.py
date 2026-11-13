"""Power figures that don't depend on FTP: Normalized Power, work and variability.

FTP-based figures (IF, TSS, W/kg) are in ``fitlib.metrics.load`` and are worked out when read,
so they follow the athlete history.
"""

from __future__ import annotations

import polars as pl

# NP smooths power over this many seconds before weighting it (Coggan).
NP_WINDOW_S = 30


def _riding_power(frame: pl.DataFrame) -> pl.Series:
    """Power for every second the timer was running, with gaps in the data counted as 0 W.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        The power series with paused seconds removed (so pauses don't count, and the seconds
        either side of a pause join up, as in other tools).
    """
    return frame.filter(pl.col("active"))["power"].cast(pl.Float64).fill_null(0.0)


def normalized_power(frame: pl.DataFrame) -> float | None:
    """Normalized Power: what a steady effort of the same physiological cost would average.

    The 30-second rolling average of power is raised to the 4th power, averaged, and the 4th
    root taken.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Watts, or ``None`` without a power meter or with under 30 s of riding.
    """
    if frame["power"].drop_nulls().is_empty():
        return None
    power = _riding_power(frame)
    if power.len() < NP_WINDOW_S:
        return None
    rolling = power.rolling_mean(window_size=NP_WINDOW_S).drop_nulls()
    return float((rolling**4).mean() ** 0.25)  # type: ignore[operator]


def kilojoules(frame: pl.DataFrame) -> float | None:
    """Work done.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Kilojoules (the sum of each riding second's watts, divided by 1000), or ``None``
        without a power meter.
    """
    if frame["power"].drop_nulls().is_empty():
        return None
    return float(_riding_power(frame).sum()) / 1000


def variability_index(np: float | None, avg_power: float | None) -> float | None:
    """How uneven the effort was: 1.0 for perfectly steady, higher for surges.

    Args:
        np: Normalized Power in watts.
        avg_power: Average power in watts.

    Returns:
        NP divided by average power, or ``None`` if either is missing or average power is 0.
    """
    if np is None or not avg_power:
        return None
    return np / avg_power
