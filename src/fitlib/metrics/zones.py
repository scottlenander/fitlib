"""Time at each power and heart-rate value, and time in training zones.

The histograms are stored per ride; zone times are worked out from them when read, using the
FTP or max heart rate in effect on the ride's date.
"""

from __future__ import annotations

import polars as pl

from fitlib.models import Histogram

# Upper bounds of power zones 1-6 as fractions of FTP; zone 7 is everything above (Coggan:
# active recovery, endurance, tempo, threshold, VO2 max, anaerobic, neuromuscular).
POWER_ZONE_BOUNDS = (0.55, 0.75, 0.90, 1.05, 1.20, 1.50)
POWER_ZONE_NAMES = (
    "Recovery", "Endurance", "Tempo", "Threshold", "VO2 max", "Anaerobic", "Neuromuscular",
)  # fmt: skip

# Upper bounds of heart-rate zones 1-4 as fractions of max HR; zone 5 is everything above.
# Zone 1 also takes anything below 50 %.
HR_ZONE_BOUNDS = (0.60, 0.70, 0.80, 0.90)
HR_ZONE_NAMES = ("Easy", "Aerobic", "Tempo", "Threshold", "Maximum")


def histogram(frame: pl.DataFrame, column: str) -> Histogram:
    """Count the riding seconds at each whole value of a channel.

    Args:
        frame: The ride's 1 Hz frame.
        column: ``"power"`` or ``"heart_rate"``.

    Returns:
        ``(value, seconds)`` pairs, lowest value first; empty if the channel wasn't recorded.
    """
    values = frame.filter(pl.col("active") & pl.col(column).is_not_null())[column]
    if values.is_empty():
        return ()
    counts = values.cast(pl.Int64).value_counts().sort(column)
    return tuple((int(v), int(n)) for v, n in counts.iter_rows())


def zone_times(hist: Histogram, reference: float, bounds: tuple[float, ...]) -> tuple[int, ...]:
    """Add up a histogram's seconds by zone.

    A value is in the first zone whose upper bound (``bound × reference``) it doesn't exceed;
    values above the last bound are in the top zone.

    Args:
        hist: Seconds at each value.
        reference: FTP in watts or max heart rate in bpm.
        bounds: Zone upper bounds as fractions of ``reference``.

    Returns:
        Seconds in each zone, ``len(bounds) + 1`` of them.
    """
    seconds = [0] * (len(bounds) + 1)
    for value, count in hist:
        fraction = value / reference
        zone = next((i for i, bound in enumerate(bounds) if fraction <= bound), len(bounds))
        seconds[zone] += count
    return tuple(seconds)
