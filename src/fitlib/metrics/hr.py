"""Heart-rate figures: aerobic decoupling."""

from __future__ import annotations

import polars as pl

from fitlib.metrics.power import normalized_power

# Decoupling means little over short rides.
MIN_DECOUPLING_S = 20 * 60


def decoupling_pct(frame: pl.DataFrame) -> float | None:
    """Aerobic decoupling (Pw:HR): how much heart rate drifted up relative to power.

    The riding seconds are split into halves. For each, NP is divided by average heart rate;
    the result is how far the second half's ratio fell below the first half's.

    Args:
        frame: The ride's 1 Hz frame.

    Returns:
        Percent (positive means heart rate drifted up for the same power; under about 5 %
        suggests good aerobic endurance), or ``None`` for rides under 20 min of riding or
        without both power and heart rate.
    """
    riding = frame.filter(pl.col("active") & pl.col("heart_rate").is_not_null())
    if riding.height < MIN_DECOUPLING_S or riding["power"].drop_nulls().is_empty():
        return None
    half = riding.height // 2
    ratios = []
    for part in (riding.slice(0, half), riding.slice(half)):
        np = normalized_power(part)
        hr = part["heart_rate"].mean()
        if np is None or not hr:
            return None
        ratios.append(np / hr)  # type: ignore[operator]
    first, second = ratios
    return (first - second) / first * 100
